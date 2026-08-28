"""演奏引擎:按音符序列的节奏模拟键盘按键(支持和弦、可停止)。"""

import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from core.keyboard_driver import KeyboardDriver


class Player(QObject):
    progress = pyqtSignal(int, int)  # 已完成音符数, 总数
    finished = pyqtSignal(bool)      # 是否完整演奏结束(False=被手动停止或出错)
    error_occurred = pyqtSignal(str)  # 演奏过程中的错误信息

    def __init__(self, keymap, driver=None, parent=None):
        super().__init__(parent)
        self._keymap = keymap
        self._driver = driver or KeyboardDriver()
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def play(self, notes, bpm, hold_ratio=0.75, gap_ms=20):
        if self.is_playing:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(list(notes), int(bpm), float(hold_ratio), float(gap_ms)),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self, notes, bpm, hold_ratio, gap_ms):
        beat_ms = 60000.0 / max(1, bpm)
        total = len(notes)
        normal = False
        error = None
        try:
            for i, note in enumerate(notes):
                if self._stop_event.is_set():
                    break
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
                self.progress.emit(i + 1, total)
            normal = not self._stop_event.is_set()
        except Exception as e:
            error = str(e)
        finally:
            self._release_all()
        if error:
            self.error_occurred.emit(error)
        self.finished.emit(normal)

    def _release_all(self):
        """保险:演奏结束/被停止时松开所有可能按住的键。"""
        for octave in ("high", "mid", "low"):
            for i in range(1, 8):
                key = self._keymap.key_for(f"{octave}_{i}")
                if key:
                    try:
                        self._driver.release_key(key)
                    except Exception:
                        pass