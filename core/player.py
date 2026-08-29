"""演奏引擎:按音符序列的节奏模拟键盘按键(支持和弦)。

三态控制:
- 开始/继续:play(start_index) 从指定进度开始
- 停止:stop() 暂停演奏,进度经 paused(done, total) 信号带出,可继续
- 重置:由调用方丢弃 paused 进度即可(下次 play 从头)
"""

import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from core.keyboard_driver import KeyboardDriver


class Player(QObject):
    progress = pyqtSignal(int, int)      # 已完成音符数, 总数(全局索引)
    finished = pyqtSignal(bool)          # 演奏自然结束(True)/出错(False)时发出
    paused = pyqtSignal(int, int)        # 停止(暂停)时发出: 已完成音符数, 总数
    error_occurred = pyqtSignal(str)     # 演奏过程中的错误信息

    def __init__(self, keymap, driver=None, parent=None):
        super().__init__(parent)
        self._keymap = keymap
        self._driver = driver or KeyboardDriver()
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def play(self, notes, bpm, hold_ratio=0.75, gap_ms=20, start_index=0):
        if self.is_playing:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(list(notes), int(bpm), float(hold_ratio), float(gap_ms), int(start_index)),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _release_all(self):
        """保险:演奏结束/暂停/被停止时松开所有可能按住的键。"""
        for octave in ("high", "mid", "low"):
            for i in range(1, 8):
                key = self._keymap.key_for(f"{octave}_{i}")
                if key:
                    try:
                        self._driver.release_key(key)
                    except Exception:
                        pass

    def _run(self, notes, bpm, hold_ratio, gap_ms, start_index):
        beat_ms = 60000.0 / max(1, bpm)
        total = len(notes)
        done = 0
        normal = False
        error = None
        try:
            for i in range(start_index, total):
                if self._stop_event.is_set():
                    break
                note = notes[i]
                dur_ms = note["dur"] * beat_ms
                keys = [self._keymap.key_for(nid) for nid in note["notes"]]
                keys = [k for k in keys if k]
                if keys:
                    self._driver.press_chord(keys)
                    time.sleep(dur_ms * hold_ratio / 1000.0)
                    self._driver.release_chord(keys)
                else:  # 休止
                    time.sleep(dur_ms / 1000.0)
                if gap_ms > 0 and not self._stop_event.is_set():
                    time.sleep(gap_ms / 1000.0)
                done = i + 1
                self.progress.emit(done, total)
            if self._stop_event.is_set():
                # 停止 = 暂停:进度经 paused 信号带出,调用方可继续或重置
                self.paused.emit(done, total)
                return
            normal = True
        except Exception as e:
            error = str(e)
        finally:
            self._release_all()
        if error:
            self.error_occurred.emit(error)
        self.finished.emit(normal)
