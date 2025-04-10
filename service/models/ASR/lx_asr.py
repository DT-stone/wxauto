# -*- coding:utf-8 -*-
import asyncio
import json
import os
import threading
import time
import uuid
from asyncio import Queue
from typing import Optional, Any

import websocket

from .vad import Vad, WavSplitter
import logging
from .base_asr import BaseASR
from pathlib import Path

current_dir = Path(__file__).resolve().parent
log_dir = current_dir.parents[2]
log_file_path = log_dir / 'log.txt'
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# client event
StartTranscription = "StartTranscription"
StopTranscription = "StopTranscription"

# server event
TranscriptionStarted = "TranscriptionStarted"
SentenceStart = "SentenceStart"
TranscriptionResultChanged = "TranscriptionResultChanged"
SentenceEnd = "SentenceEnd"
TranscriptionCompleted = "TranscriptionCompleted"

host = '116.196.96.191'


class LxAsr(BaseASR):

    def __init__(self, queue):
        self.ws_addr = f"ws://{host}/asr/v0.8"
        self.asr_client = LxAsrOnline(ws_addr=self.ws_addr, callback=LxAsrCallback(), queue=queue)
        self.asr_client.set_sample_rate(16000)
        self.asr_client.start()
        pass

    async def post_audio(self, combined_audio: bytes, lang: str = "auto") -> str:
        self.asr_client.send(combined_audio)
        self.asr_client.stats.cal()
        self.asr_client.stats.log()
        result = ''

        # 改为 on_message 中异步队列传递
        # for msg in self.asr_client.stats.msg_lst:
        #     print(f'asr  msg info :{msg}')
        #     if msg['header']['event_name'] in ['SentenceEnd']:
        #         result = msg['payload']['result']
        # result = self.asr_client.stats.msg_lst[-1]['payload']['result']
        # print(f'asr 同步识别结果:{result}')

        return result


class LxAsrError(Exception):
    pass


class LxAsrCallback:
    def on_message(self, message: dict) -> None:
        """
            onmessage 事件
        Args:
            message (dict): server_msg 之一
        {'header': {'status': 200, 'status_message': 'ok', 'event_name': 'TranscriptionResultChanged', 'task_id': 'e68f9fa4-1661-11ef-8d8e-acde48001122'},
        'payload': {'index': 1, 'result': '好像他没有钱那个向我培训的告知书', 'end_time': 3965, 'start_time': 470, 'vad_start_time': 0, 'vad_end_time': -1, 'audio_received_ms': 4580, 'words': []}}
            {'header': {'event_name': 'TranscriptionStarted', 'status': 200, 'status_message': 'ok', 'task_id': '5c6e46f0-ee1e-11ef-a1f9-acde48001122'}}
        Returns:

        """
        try:
            if message['header']['status'] == 200:
                result = message['payload']['result']
                logging.info(f'LxAsrCallback on_message result:{result}')
        except Exception as e:
            logging.error(f'LxAsrCallback on_message error:{e}')

    def on_error(self, message: dict):
        """

        Args:
            message ():
                {
                    "type": "xxx",
                    "msg": "xxx"
                }
        Returns:

        """
        logging.info(f'LxAsrCallback on_error :{message}')


class LxAsrOnline:
    class State:
        INIT = "INIT"
        CONNECTED = "CONNECTED"
        STARTED = "STARTED"
        STOPPED = "STOPPED"
        ERROR = "ERROR"

    class VadState:
        WAIT_START = "WAIT_START"
        WAIT_END = "WAIT_END"

    def __init__(self, ws_addr: str, callback: LxAsrCallback, queue: Queue):
        self.asr_result_queue = queue
        self._ws_addr = ws_addr
        self._callback = callback

        self._ping_interval = 20
        self._ping_timeout = 15

        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[dict] = None
        self._state = self.State.INIT
        self._cond = threading.Condition()

        self._vad_obj = Vad()
        self._vad_state = self.VadState.WAIT_START

        self._task_id = str(uuid.uuid1())
        self._payload = {
            "sample_rate": 8000,
            "enable_punctuation": False,
            "punctuation_threshold": 300,
            "enable_words": False,
        }

        self._stats = LxAsrTimeStats()
        self._first_send = True

        self._first_task_id = ""
        self._pcm_ms = 0
        self._pcm_length_per_ms = self._payload["sample_rate"] // 1000 * 2

        self.loop = asyncio.get_event_loop()

    @property
    def stats(self) -> "LxAsrTimeStats":
        return self._stats

    def set_vad(self, vad_obj: Optional[Vad]) -> None:
        """
        设置为 None 表示禁用 vad。
        """
        self._vad_obj = vad_obj

    def set_task_id(self, task_id: str) -> None:
        self._task_id = task_id

    def set_sample_rate(self, sample_rate: int) -> None:
        if sample_rate not in (8000, 16000):
            raise ValueError("sample_rate should be 8000 or 16000")
        self._payload["sample_rate"] = sample_rate
        self._pcm_length_per_ms = self._payload["sample_rate"] // 1000 * 2

    def set_enable_punctuation(self, flag: bool) -> None:
        self._payload["enable_punctuation"] = flag

    def set_punctuation_threshold(self, threshold_ms: int) -> None:
        if threshold_ms < 0:
            raise ValueError("punctuation_threshold should be larger than 0")
        self._payload["punctuation_threshold"] = threshold_ms

    def set_enable_words(self, flag: bool) -> None:
        self._payload["enable_words"] = flag

    def set_payload_extra(self, key: str, value: Any) -> None:
        self._payload[key] = value

    def set_ping_interval(self, ping_interval: int) -> None:
        if ping_interval < 0:
            raise ValueError("ping_interval should be larger than 0")
        self._ping_interval = ping_interval

    def set_ping_timeout(self, ping_timeout: int) -> None:
        if ping_timeout < 0:
            raise ValueError("ping_timeout should be larger than 0")
        self._ping_timeout = ping_timeout

    def start(self) -> None:
        assert self._state == self.State.INIT
        self._connect()
        self._wait_connected()
        assert self._state == self.State.CONNECTED
        self._send_start_msg()
        self._wait_started()
        assert self._state == self.State.STARTED

    def send(self, pcm: bytes) -> None:
        if self._state != self.State.STARTED:
            raise RuntimeError("AsrClient is not started")
        if self._first_send:
            self._stats.start_time = time.time()
            self._first_send = False
        self._send_binary(pcm)
        self._pcm_ms += len(pcm) // self._pcm_length_per_ms
        if self._vad_obj:
            # pcm 需要为指定长度的二进制数据, 2*80 的倍数,填充 pcm 数据
            # 计算 num_points
            num_points = len(pcm) // 2

            # 确保 num_points 是 _num_points_per_chunk 的倍数
            if num_points % self._vad_obj._num_points_per_chunk != 0:
                padding_length = (self._vad_obj._num_points_per_chunk - (
                        num_points % self._vad_obj._num_points_per_chunk)) * 2
                pcm += b'\x00' * padding_length
                print(len(pcm), '数据位数不够,补充中...')
            self._vad_obj.accept_waveform(pcm)
            if self._vad_state == self.VadState.WAIT_START:
                idx = self._vad_obj.find_start()
                if idx != -1:
                    self._vad_state = self.VadState.WAIT_END
                    self._stats.vad_start_times.append(idx / 1000)
                    self._stats.result_changed_times.append(
                        [(idx / 1000, None)]
                    )
            elif self._vad_state == self.VadState.WAIT_END:
                idx = self._vad_obj.find_end()
                if idx != -1:
                    # if self._first_task_id == "":
                    #     self._first_task_id = self._task_id
                    # task_id = "{}.{}".format(self._first_task_id, idx)
                    # self.set_task_id(task_id)
                    # logger.info("task_id: {}, pcm_ms: {}".format(task_id, self._pcm_ms))

                    self._vad_state = self.VadState.WAIT_START
                    self._stats.vad_end_times.append(idx / 1000)
                    a = time.time()
                    self._send_stop_msg()
                    self._wait_stopped()
                    self._send_start_msg()
                    self._wait_started()
                    logging.debug("stop to start cost: %s" % (time.time() - a))

    def stop(self) -> None:
        if self._state == self.State.STARTED:
            self._send_stop_msg()
            self._wait_stopped()
            with self._cond:
                self._state = self.State.STOPPED
        if self._ws:
            if self._thread and self._thread.is_alive():
                self._ws.keep_running = False
                self._thread.join()
            self._ws.close()
            self._ws = None

    def _connect(self) -> None:
        self._ws = websocket.WebSocketApp(
            self._ws_addr,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        def _run():
            try:
                self._ws.run_forever(
                    ping_interval=self._ping_interval,
                    ping_timeout=self._ping_timeout,
                    suppress_origin=True,
                )
            except Exception as e:
                self._error = {
                    "type": "websocket_start_error",
                    "msg": str(e),
                }
                with self._cond:
                    self._state = self.State.ERROR
                    self._cond.notify()

        self._thread = threading.Thread(
            target=_run,
        )
        self._thread.daemon = True
        self._thread.start()

    def _wait_connected(self) -> None:
        with self._cond:
            while True:
                if (
                        self._state == self.State.CONNECTED
                        or self._state == self.State.ERROR
                ):
                    break
                self._cond.wait(timeout=1)
        if self._error:
            raise LxAsrError(self._error["msg"])

    def _send_start_msg(self) -> None:
        start_msg = {
            "header": {
                "event_name": StartTranscription,
                "task_id": self._task_id,
            },
            "payload": self._payload,
        }
        self._send_text(json.dumps(start_msg))

    def _wait_started(self) -> None:
        with self._cond:
            while True:
                if (
                        self._state == self.State.STARTED
                        or self._state == self.State.ERROR
                ):
                    break
                self._cond.wait(timeout=1)
        if self._error:
            raise LxAsrError(self._error["msg"])

    def _send_stop_msg(self) -> None:
        stop_msg = {
            "header": {
                "event_name": StopTranscription,
            }
        }
        self._send_text(json.dumps(stop_msg))

    def _wait_stopped(self) -> None:
        with self._cond:
            while True:
                if (
                        self._state == self.State.STOPPED
                        or self._state == self.State.ERROR
                ):
                    break
                self._cond.wait(timeout=1)
        if self._error:
            raise LxAsrError(self._error["msg"])

    def _send_text(self, s: str) -> None:
        assert self._ws is not None
        self._ws.send(s, opcode=websocket.ABNF.OPCODE_TEXT)

    def _send_binary(self, b: bytes) -> None:
        assert self._ws is not None
        self._ws.send(b, opcode=websocket.ABNF.OPCODE_BINARY)

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        with self._cond:
            self._state = self.State.CONNECTED
            self._cond.notify()

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        msg_dict = json.loads(message)
        if msg_dict["header"]["status"] != 200:
            self._error = {
                "type": "server_error",
                "status": msg_dict["header"]["status"],
                "msg": msg_dict["header"]["status_message"],
            }
            self._callback.on_error(self._error)
            with self._cond:
                self._state = self.State.ERROR
                self._cond.notify()
            return

        event_name = msg_dict["header"]["event_name"]
        t = time.time()
        if event_name == TranscriptionStarted:
            with self._cond:
                self._state = self.State.STARTED
                self._cond.notify()
        elif event_name == TranscriptionCompleted:
            self._stats.completed_times.append(t)
            with self._cond:
                self._state = self.State.STOPPED
                self._cond.notify()
        elif event_name == SentenceEnd:
            self._stats.sentence_end_times.append(t)
            if (
                    self._stats.result_changed_times
                    and msg_dict["payload"]["result"] != ""
            ):
                self._stats.result_changed_times[-1].append((t, msg_dict))
        elif event_name == TranscriptionResultChanged:
            if self._stats.result_changed_times:
                self._stats.result_changed_times[-1].append((t, msg_dict))

        if event_name in (
                # SentenceStart,
                # TranscriptionResultChanged,
                SentenceEnd,
        ):
            self._stats.msg_lst.append(msg_dict)
            # 解决第一次的识别结果在第二次调用的时候才返回的问题 . 直接把结果放到异步队列,不再使用 stats 中的 last_msg
            msg = msg_dict["payload"]["result"]
            print(f'asr client stats contains msg len:{len(self._stats.msg_lst)},\n - {msg}')
            try:
                # asyncio.create_task(self.enqueue(msg))
                # future future.result()会阻塞线程 等待结果
                asyncio.run_coroutine_threadsafe(
                    self.asr_result_queue.put(msg),
                    self.loop
                )
                # future.result()阻塞线程 和 await asyncio.wait_for(self.asr_result_queue.get(), timeout=5)   相互形成了死锁 放弃阻塞
                # future.result()

                # self.loop.call_soon_threadsafe(self.asr_result_queue.put, msg)
                print(f'异步事件存放数据完毕,member count:{self.asr_result_queue.qsize()}')
            except Exception as e:
                print(e)

        # self._callback.on_message(msg_dict)

    def handle_asr_result_sync(self, msg_dict):
        # 处理 ASR 结果入队
        loop = asyncio.get_event_loop()

        def enqueue_sync():
            print(f'存放消息: {msg_dict["payload"]["result"]}')
            loop.create_task(self.enqueue(msg_dict["payload"]["result"]))
            print('存放完毕')

        threading.Thread(target=enqueue_sync).start()

    async def enqueue(self, msg):
        await self.asr_result_queue.put(msg)

    def _on_error(self, ws: websocket.WebSocketApp, error: Any) -> None:
        self._error = {"type": "websocket_error", "msg": str(error)}
        if self._state == self.State.STARTED:
            self._callback.on_error(self._error)
        with self._cond:
            self._state = self.State.ERROR
            self._cond.notify()

    def _on_close(
            self,
            ws: websocket.WebSocketApp,
            close_status_code: Optional[int],
            close_msg: Optional[str],
    ) -> None:
        if not self._error:
            self._error = {
                "type": "websocket_close",
                "status": close_status_code,
                "msg": close_msg,
            }
        if self._state == self.State.STARTED:
            self._callback.on_error(self._error)
        with self._cond:
            self._state = self.State.ERROR
            self._cond.notify()


class LxAsrTimeStats:
    def __init__(self):
        self.start_time = time.time()
        self.vad_start_times = []
        self.vad_end_times = []
        self.sentence_end_times = []
        self.completed_times = []

        self.result_changed_times = []
        self.result_changed_sub_vad_start = []
        self.result_changed_stats = []
        self.result_changed_sub_vad_start_1 = []
        self.result_changed_sub_vad_start_2 = []
        self.result_changed_sub_vad_start_3 = []

        self.completed_sub_vad_end = []

        self.msg_lst = []

    def cal(self) -> None:
        self.sentence_end_times = [
            e - self.start_time for e in self.sentence_end_times
        ]
        self.completed_times = [
            e - self.start_time for e in self.completed_times
        ]

        self.completed_sub_vad_end.clear()
        for i in range(len(self.vad_end_times)):
            a = self.completed_times[i] - self.vad_end_times[i]
            self.completed_sub_vad_end.append(a)

        self.result_changed_sub_vad_start.clear()
        for item in self.result_changed_times:
            if len(item) >= 2:
                d = item[1][0] - item[0][0] - self.start_time
                self.result_changed_sub_vad_start.append(d)
                self.result_changed_stats.append((item[0][0], d, item[1][1]))

                msg = item[1][1]
                d = (
                        msg["payload"]["audio_received_ms"]
                        - msg["payload"]["vad_start_time"]
                )
                self.result_changed_sub_vad_start_1.append(d)

                d = (
                        msg["payload"]["audio_received_ms"]
                        - msg["payload"]["start_time"]
                )
                self.result_changed_sub_vad_start_2.append(d)

        prev_event_name = ""
        for msg_dict in self.msg_lst:
            cur_event_name = msg_dict["header"]["event_name"]
            p = msg_dict["payload"]
            if (
                    prev_event_name == SentenceStart
                    and cur_event_name == TranscriptionResultChanged
                    and p["vad_start_time"] != p["start_time"]
            ):
                d = p["audio_received_ms"] - p["vad_start_time"]
                self.result_changed_sub_vad_start_3.append(d)
            prev_event_name = cur_event_name

    def log(self) -> None:
        logging.info("start_time: %s" % (self.start_time,))
        logging.info(
            "vad_start_times: %s %s"
            % (
                self.vad_start_times,
                len(self.vad_start_times),
            )
        )
        logging.info(
            "vad_end_times: %s %s"
            % (
                self.vad_end_times,
                len(self.vad_end_times),
            )
        )
        logging.info(
            "sentence_end_times: %s %s"
            % (
                self.sentence_end_times,
                len(self.sentence_end_times),
            )
        )
        logging.info(
            "completed_times: %s %s"
            % (
                self.completed_times,
                len(self.completed_times),
            )
        )
        if self.completed_sub_vad_end:
            logging.info(
                "completed_sub_vad_end: %s %s"
                % (
                    self.completed_sub_vad_end,
                    sum(self.completed_sub_vad_end)
                    / len(self.completed_sub_vad_end),
                )
            )
        if self.result_changed_stats:
            logging.info(
                "result_changed_stats: %s %s"
                % (
                    self.result_changed_stats,
                    len(self.result_changed_stats),
                )
            )


import wave

if __name__ == "__main__":
    pass
