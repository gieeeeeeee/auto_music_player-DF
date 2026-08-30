"""延迟校准测试:确定性采样统计、补偿值钳制、取消路径、Player 补偿生效、配置写回。

运行: python -m unittest tests.test_latency_calibration -v
"""

import os
import tempfile
import threading
import time
import unittest

from core.keymap import KeyMap
from core.latency_calibration import LatencyCalibrator, MAX_COMPENSATION_MS
from core.player import Player
from gui.calibration_dialog import update_player_config_value

MAPPING = {
    "high": ["Q", "W", "E", "R", "T", "Y", "U"],
    "mid": ["A", "S", "D", "F", "G", "H", "J"],
    "low": ["Z", "X", "C", "V", "B", "N", "M"],
}


class FakeClock:
    """虚拟时钟:等待瞬间完成,驱动延迟由 driver 注入 → 测量完全确定。"""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class InstantWaiter:
    def __init__(self, clock):
        self._clock = clock

    def __call__(self, seconds):
        self._clock.now += max(0.0, seconds)


class LaggyDriver:
    """press_key 消耗固定时长,模拟 SendInput 调用滞后。"""

    def __init__(self, clock, lag_s):
        self._clock = clock
        self._lag = lag_s

    def press_key(self, k):
        self._clock.now += self._lag

    def release_key(self, k):
        pass


class TestCalibrator(unittest.TestCase):
    def _run(self, lag_s, samples=16, stop_event=None, on_sample=None):
        clock = FakeClock()
        calibrator = LatencyCalibrator(
            LaggyDriver(clock, lag_s),
            KeyMap(MAPPING),
            clock=clock,
            wait_fn=InstantWaiter(clock),
            samples=samples,
        )
        return calibrator.run(stop_event, on_sample)

    def test_deterministic_stats(self):
        result = self._run(0.003)
        self.assertEqual(result.samples, 16)
        self.assertAlmostEqual(result.avg_lag_ms, 3.0, places=6)
        self.assertAlmostEqual(result.max_lag_ms, 3.0, places=6)
        self.assertAlmostEqual(result.std_lag_ms, 0.0, places=6)
        self.assertEqual(result.compensation_ms, 3)
        self.assertTrue(result.stable)
        self.assertFalse(result.cancelled)
        self.assertIn("建议补偿值 3ms", result.format())

    def test_zero_lag(self):
        result = self._run(0.0)
        self.assertEqual(result.compensation_ms, 0)
        self.assertAlmostEqual(result.avg_lag_ms, 0.0, places=6)

    def test_compensation_clamped(self):
        result = self._run(0.5)   # 平均 500ms → 钳制到上限
        self.assertEqual(result.compensation_ms, MAX_COMPENSATION_MS)

    def test_unstable_detection(self):
        """滞后在两个值间交替 → 标准差大 → 判定为不稳定。"""
        clock = FakeClock()
        driver = _AlternatingLagDriver(clock, [0.001, 0.030])
        calibrator = LatencyCalibrator(
            driver, KeyMap(MAPPING), clock=clock, wait_fn=InstantWaiter(clock), samples=16
        )
        result = calibrator.run()
        self.assertFalse(result.stable)
        self.assertIn("波动较大", result.format())

    def test_cancel_before_start(self):
        ev = threading.Event()
        ev.set()
        result = self._run(0.001, stop_event=ev)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.samples, 0)

    def test_cancel_midway(self):
        ev = threading.Event()

        def stop_after_first(_count):
            ev.set()

        result = self._run(0.001, stop_event=ev, on_sample=stop_after_first)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.samples, 1)


class _AlternatingLagDriver(LaggyDriver):
    def __init__(self, clock, lags_s):
        super().__init__(clock, 0)
        self._lags = lags_s
        self._i = 0

    def press_key(self, k):
        self._clock.now += self._lags[self._i % len(self._lags)]
        self._i += 1


class TimestampDriver:
    """记录每次 press_chord 的真实时刻,用于验证 Player 补偿生效。"""

    def __init__(self):
        self.press_times = []

    def press_chord(self, keys):
        self.press_times.append(time.perf_counter())

    def release_chord(self, keys):
        pass

    def press_key(self, k):
        pass

    def release_key(self, k):
        pass


class TestPlayerCompensation(unittest.TestCase):
    """绝对时钟调度下,补偿量使音符实际间隔 = 理论间隔 - 补偿值。"""

    def _press_gaps(self, comp):
        driver = TimestampDriver()
        player = Player(KeyMap(MAPPING), driver=driver, latency_compensation_ms=comp)
        notes = [{"notes": ["mid_1"], "dur": 1.0}] * 5
        player.play(notes, bpm=200, hold_ratio=0.5, gap_ms=0)   # 间隔 300ms
        deadline = time.time() + 5
        while player.is_playing and time.time() < deadline:
            time.sleep(0.01)
        gaps = [b - a for a, b in zip(driver.press_times, driver.press_times[1:])]
        return gaps

    def test_no_compensation_keeps_theory_interval(self):
        gaps = self._press_gaps(0)
        for gap in gaps:
            self.assertAlmostEqual(gap, 0.3, delta=0.05)

    def test_compensation_advances_timeline(self):
        """补偿使整条时间轴提前一个常量:首个间隔 = 理论 - 补偿;
        后续间隔保持理论值(绝对时钟调度不累积漂移的固有特性)。"""
        gaps = self._press_gaps(100)
        self.assertAlmostEqual(gaps[0], 0.2, delta=0.05)    # 300 - 100
        for gap in gaps[1:]:
            self.assertAlmostEqual(gap, 0.3, delta=0.05)


class TestConfigPatch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "config.yaml")

    def tearDown(self):
        for f in os.listdir(self.dir):
            os.remove(os.path.join(self.dir, f))
        os.rmdir(self.dir)

    def _write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def _read(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_update_existing_key(self):
        self._write("app:\n  data_dir: data\n\nplayer:\n  # 热键\n  stop_hotkey: F8\n  latency_compensation_ms: 0\n")
        update_player_config_value(self.path, "latency_compensation_ms", 12)
        text = self._read()
        self.assertIn("latency_compensation_ms: 12", text)
        self.assertNotIn("latency_compensation_ms: 0", text)
        self.assertIn("# 热键", text)   # 注释保留
        self.assertIn("stop_hotkey: F8", text)

    def test_insert_missing_key(self):
        self._write("player:\n  # 热键\n  stop_hotkey: F8\n")
        update_player_config_value(self.path, "latency_compensation_ms", 7)
        text = self._read()
        self.assertIn("latency_compensation_ms: 7", text)
        self.assertIn("# 热键", text)
        lines = text.splitlines()
        self.assertLess(lines.index("player:"), lines.index("  latency_compensation_ms: 7"))

    def test_append_without_player_section(self):
        self._write("app:\n  data_dir: data\n")
        update_player_config_value(self.path, "latency_compensation_ms", 5)
        self.assertIn("latency_compensation_ms: 5", self._read())

    def test_does_not_touch_other_sections(self):
        self._write("player:\n  stop_hotkey: F8\nother:\n  latency_compensation_ms: 99\n")
        update_player_config_value(self.path, "latency_compensation_ms", 3)
        text = self._read()
        self.assertIn("latency_compensation_ms: 3", text)
        self.assertIn("latency_compensation_ms: 99", text)   # other 段不受影响


if __name__ == "__main__":
    unittest.main()
