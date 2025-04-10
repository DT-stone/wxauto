# -*- coding:utf-8 -*-

# @Time    : 2023/10/22 17:21
# @Author  : zengwenjia
# @Email   : zengwenjia@lingxi.ai
# @File    : vad.py
# @Software: LLM_internal

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
from typing import List, Tuple

import webrtcvad


class VadDefault:
    @property
    def VAD_MODE(self) -> int:
        return 3

    @property
    def SAMPLE_RATE(self) -> int:
        return 8000

    @property
    def CHUNK_SIZE_MS(self) -> int:
        return 10

    @property
    def START_WINDOW_SIZE(self) -> int:
        return 20

    @property
    def START_THRESHOLD(self) -> int:
        return 16

    @property
    def END_WINDOW_SIZE(self) -> int:
        return 60

    @property
    def END_THRESHOLD(self) -> int:
        return 54


vad_default = VadDefault()


class Vad:
    def __init__(self):
        self._vad = webrtcvad.Vad()
        self._vad.set_mode(vad_default.VAD_MODE)

        self._sample_rate = vad_default.SAMPLE_RATE
        self._chunk_size_ms = vad_default.CHUNK_SIZE_MS
        self._cal_num_points_per_chunk()

        self._vad_window = VadWindow()

    def _cal_num_points_per_chunk(self) -> None:
        self._num_points_per_chunk = (
            self._sample_rate * self._chunk_size_ms // 1000
        )

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def chunk_size_ms(self) -> int:
        return self._chunk_size_ms

    @property
    def num_points_per_chunk(self) -> int:
        return self._num_points_per_chunk

    def reset(self) -> None:
        self._vad_window.reset()

    def set_max_silence_ms(self, max_silence_ms: int) -> None:
        end_window_size = max_silence_ms // self._chunk_size_ms
        end_threshold = end_window_size * 9 // 10
        return self._vad_window.set_end(end_window_size, end_threshold)

    def set_start(self, start_window_size: int, start_threshold: int) -> None:
        return self._vad_window.set_start(start_window_size, start_threshold)

    def set_end(self, end_window_size: int, end_threshold: int) -> None:
        return self._vad_window.set_end(end_window_size, end_threshold)

    def set_mode(self, mode: int) -> None:
        """
        Args:
            mode(int): 0, 1, 2 or 3.
                0 更倾向把声音当作人声
                3 更倾向把声音当作静音
        """
        assert mode in (0, 1, 2, 3)
        self._vad.set_mode(mode)

    def set_sample_rate(self, sample_rate: int) -> None:
        assert sample_rate in (8000, 16000, 32000, 48000)
        self._sample_rate = sample_rate
        self._cal_num_points_per_chunk()

    def set_chunk_size_ms(self, chunk_size_ms: int) -> None:
        assert chunk_size_ms in (10, 20, 30)
        self._chunk_size_ms = chunk_size_ms
        self._cal_num_points_per_chunk()

    def accept_waveform(self, pcm: bytes) -> None:
        # 只支持位宽为 2 的 pcm
        assert len(pcm) % 2 == 0
        num_points = len(pcm) // 2
        assert num_points % self._num_points_per_chunk == 0

        step = self._num_points_per_chunk * 2
        for i in range(0, len(pcm), step):
            chunk = pcm[i : i + step]
            is_speech: bool = self._vad.is_speech(chunk, self._sample_rate)
            self._vad_window.put(is_speech)

    def find_start(self) -> int:
        start_index = self._vad_window.find_start()
        if start_index == -1:
            return -1
        index_ms = self._index_to_ms(start_index)
        return index_ms

    def find_end(self) -> int:
        end_index = self._vad_window.find_end()
        if end_index == -1:
            return -1
        index_ms = self._index_to_ms(end_index)
        return index_ms

    def _index_to_ms(self, index: int) -> int:
        assert index >= 0
        return self._chunk_size_ms * index


class VadWindow:
    def __init__(self):
        self._start_window_size = vad_default.START_WINDOW_SIZE
        self._start_threshold = vad_default.START_THRESHOLD
        self._end_window_size = vad_default.END_WINDOW_SIZE
        self._end_threshold = vad_default.END_THRESHOLD

        self._max_window_size = max(
            self._start_window_size, self._end_window_size
        )

        self._window = []
        self._num_speech_start = -1
        self._num_speech_end = -1
        self._last_offset = -1
        self._window_offset = 0

    def set_start(self, start_window_size: int, start_threshold: int) -> None:
        if not (0 < start_threshold <= start_window_size):
            raise ValueError("ensure 0 < start_threshold <= start_window_size")
        self._start_window_size = start_window_size
        self._start_threshold = start_threshold
        self._max_window_size = max(
            self._start_window_size, self._end_window_size
        )

    def set_end(self, end_window_size: int, end_threshold: int) -> None:
        if not (0 < end_threshold <= end_window_size):
            raise ValueError("ensure 0 < end_threshold <= end_window_size")
        self._end_window_size = end_window_size
        self._end_threshold = end_threshold
        self._max_window_size = max(
            self._start_window_size, self._end_window_size
        )

    def reset(self) -> None:
        self._window.clear()
        self._num_speech_start = -1
        self._num_speech_end = -1
        self._last_offset = -1
        self._window_offset = 0

    def put(self, is_speech: bool) -> None:
        self._window.append(is_speech)

    def find_start(self) -> int:
        self._num_speech_end = -1
        window_size = self._start_window_size
        if len(self._window) < window_size:
            return -1

        cur_window_length = len(self._window)
        cur_offset = self._last_offset + 1
        if cur_offset >= cur_window_length:
            return -1

        idx = -1
        if self._num_speech_start < 0:
            if cur_offset < window_size - 1:
                cur_offset = window_size - 1

            num_speech_start = sum(
                self._window[cur_offset - window_size + 1 : cur_offset + 1]
            )
            self._num_speech_start = num_speech_start
            if num_speech_start >= self._start_threshold:
                idx = cur_offset - window_size + 1
            cur_offset += 1

        if idx == -1:
            i = cur_offset - window_size
            num_speech_start = self._num_speech_start
            while cur_offset < cur_window_length:
                if self._window[cur_offset]:
                    num_speech_start += 1
                if self._window[i]:
                    num_speech_start -= 1
                i += 1
                cur_offset += 1
                if num_speech_start >= self._start_threshold:
                    idx = i
                    break
            self._num_speech_start = num_speech_start

        if idx != -1:
            idx = self._window_offset + idx

        self._last_offset = cur_offset - 1
        start_idx = cur_offset - self._max_window_size
        if start_idx >= 0:
            self._window_offset += start_idx
            self._window = self._window[start_idx:]
            self._last_offset -= start_idx

        return idx

    def find_end(self) -> int:
        self._num_speech_start = -1
        window_size = self._end_window_size
        if len(self._window) < window_size:
            return -1

        cur_window_length = len(self._window)
        cur_offset = self._last_offset + 1
        if cur_offset >= cur_window_length:
            return -1

        idx = -1
        if self._num_speech_end < 0:
            if cur_offset < window_size - 1:
                cur_offset = window_size - 1
            num_speech_end = sum(
                self._window[cur_offset - window_size + 1 : cur_offset + 1]
            )
            self._num_speech_end = num_speech_end
            if (self._end_window_size - num_speech_end) >= self._end_threshold:
                idx = cur_offset - window_size + 1
            cur_offset += 1

        if idx == -1:
            i = cur_offset - window_size
            num_speech_end = self._num_speech_end
            while cur_offset < cur_window_length:
                if self._window[cur_offset]:
                    num_speech_end += 1
                if self._window[i]:
                    num_speech_end -= 1
                i += 1
                cur_offset += 1
                if (
                    self._end_window_size - num_speech_end
                ) >= self._end_threshold:
                    idx = i
                    break
            self._num_speech_end = num_speech_end

        if idx != -1:
            idx = self._window_offset + idx

        self._last_offset = cur_offset - 1
        start_idx = cur_offset - self._max_window_size
        if start_idx >= 0:
            self._window_offset += start_idx
            self._window = self._window[start_idx:]
            self._last_offset -= start_idx

        return idx


class WavSplitter:
    def __init__(self):
        self._vad = Vad()

    def set_vad(self, vad: "Vad") -> None:
        self._vad = vad

    def split_pcm(
        self, pcm: bytes, silence_left: int = 100, silence_right: int = 100
    ) -> List[Tuple[int, int]]:
        """
        Args:
            pcm (bytes): pcm 数据。
            silence_left (int): 左边留的静音长度，以 ms 为单位。
            silence_right (int): 右边留的静音长度，以 ms 为单位。
        Returns:
            List[Tuple[int, int]]: 分割的区间，每个区间表示一段音频，以 ms 为单位。
                [
                    (10, 100),
                    (150, 500),
                    ...
                ]
        """
        self._vad.reset()

        starts = []
        ends = []
        state = "find_start"
        num_points_per_ms = self._vad.sample_rate // 1000
        step = num_points_per_ms * self._vad.chunk_size_ms * 2
        for i in range(0, len(pcm), step):
            pcm_chunk = pcm[i : i + step]
            if len(pcm_chunk) < step:
                pcm_chunk += b"\x00" * (step - len(pcm_chunk))
            self._vad.accept_waveform(pcm_chunk)
            if state == "find_start":
                start_ms = self._vad.find_start()
                if start_ms != -1:
                    starts.append(start_ms)
                    state = "find_end"
            elif state == "find_end":
                end_ms = self._vad.find_end()
                if end_ms != -1:
                    ends.append(end_ms)
                    state = "find_start"
        if len(starts) != len(ends):
            assert state == "find_end"
            while True:
                pcm_chunk = b"\x00" * step
                self._vad.accept_waveform(pcm_chunk)
                end_ms = self._vad.find_end()
                if end_ms != -1:
                    ends.append(end_ms)
                    state = "find_start"
                    break
        assert len(starts) == len(ends)
        if starts:
            pcm_duration_ms = len(pcm) // 2 // num_points_per_ms
            if ends[-1] > pcm_duration_ms:
                ends[-1] = pcm_duration_ms
            if silence_left > 0:
                for i in range(len(starts)):
                    if starts[i] - silence_left >= 0:
                        starts[i] -= silence_left
            if silence_right > 0:
                for i in range(len(ends)):
                    if ends[i] + silence_right <= pcm_duration_ms:
                        ends[i] += silence_right
                    else:
                        ends[i] = pcm_duration_ms
            for i in range(len(starts)):
                if starts[i] >= ends[i]:
                    raise ValueError(
                        "starts[{i}] >= ends[{i}]: {v1} >= {v2}".format(
                            i=i, v1=starts[i], v2=ends[i]
                        )
                    )
            for i in range(len(starts) - 1):
                if ends[i] >= starts[i + 1]:
                    raise ValueError(
                        "ends[{i}] >= starts[{i_1}]: {v1} >= {v2}".format(
                            i=i, i_1=i + 1, v1=ends[i], v2=starts[i + 1]
                        )
                    )
        res: List[Tuple[int, int]] = []
        for i in range(len(starts)):
            res.append((starts[i], ends[i]))
        return res


def _test_vad_window():
    vad_window = VadWindow()
    idx = vad_window.find_start()
    print(idx)
    idx = vad_window.find_end()
    print(idx)

    is_speech_lst = [
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ]
    state = "wait_start"
    for is_speech in is_speech_lst:
        vad_window.put(is_speech)
        if state == "wait_start":
            idx = vad_window.find_start()
            print("start_idx:", idx)
            if idx != -1:
                state = "wait_end"
        elif state == "wait_end":
            idx = vad_window.find_end()
            print("end_idx:", idx)
            if idx != -1:
                state = "wait_start"


def main():
    import wave

    wav_file = "test.wav"

    sample_rate = 8000
    vad = Vad()
    vad.set_max_silence_ms(800)
    # vad.set_end(80, 72)
    vad.set_sample_rate(sample_rate)

    interval = 20
    with wave.open(wav_file) as f:
        frame_rate = f.getframerate()
        # num_frames = f.getnframes()
        num_frames_per_time = int(frame_rate * interval / 1000)
        starts = []
        ends = []
        state = "wait_start"
        while True:
            data = f.readframes(num_frames_per_time)
            if data == b"":
                break
            vad.accept_waveform(data)
            if state == "wait_start":
                start_ms = vad.find_start()
                if start_ms != -1:
                    starts.append(start_ms)
                    state = "wait_end"
            elif state == "wait_end":
                end_ms = vad.find_end()
                if end_ms != -1:
                    ends.append(end_ms)
                    state = "wait_start"
    for i in range(len(starts)):
        start_ms = starts[i]
        end_ms = ends[i]
        print(start_ms, end_ms)


if __name__ == "__main__":
    # _test_vad_window()
    main()
