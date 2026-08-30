"""演奏可观测性测试:日志格式、统计计算、写盘失败降级、Player 集成。

运行: python -m unittest tests.test_play_logger -v
"""

import json
import os
import shutil
import time
import unittest

from core.keymap import KeyMap
from core.play_logger import DEV_WARN_MS, PlayLogger, PlaySummary
from core.player import Player
from tests.test_player_stop import FakeDriver

MAPPING = {
    "high": ["Q", "W", "E", "R", "T", "Y", "U"],
    "mid": ["A", "S", "D", "F", "G", "H", "J"],
    "low": ["Z", "X", "C", "V", "B", "N", "M"],
}

NOTES = [
    {"notes": ["mid_1"], "dur": 1.0},
    {"notes": ["mid_1", "mid_3"], "dur": 1.0},
    {"notes": [], "dur": 1.0},
]


def wait_done(player, timeout=5.0):
    deadline = time.time() + timeout
    while player.is_playing and time.time() < deadline:
        time.sleep(0.01)
    return not player.is_playing


class TestPlaySummary(unittest.TestCase):
    def test_success_rate(self):
        s = PlaySummary(logged_notes=4, key_failures=1)
        self.assertEqual(s.success_rate, 0.75)
        self.assertIsNone(PlaySummary().success_rate)

    def test_format(self):
        s = PlaySummary(
            total_notes=3, completed_notes=3, logged_notes=3,
            avg_dev_ms=1.23, max_dev_ms=5.0, dev_over_ratio=0.25,
        )
        text = s.format()
        self.assertIn("完成 3/3 音符", text)
        self.assertIn("按键成功率 100%", text)
        self.assertIn("平均间隔偏差 1.2ms", text)
        self.assertIn("最大 5ms", text)
        self.assertIn(f"偏差>{DEV_WARN_MS:g}ms 占比 25%", text)

    def test_format_empty(self):
        self.assertEqual(PlaySummary().format(), "完成 0/0 音符")

    def test_format_error(self):
        text = PlaySummary(error="boom").format()
        self.assertIn("出错: boom", text)


class TestPlayLogger(unittest.TestCase):
    def setUp(self):
        self.log_dir = os.path.join("data", "test_play_logs")
        if os.path.isdir(self.log_dir):
            shutil.rmtree(self.log_dir)

    def tearDown(self):
        if os.path.isdir(self.log_dir):
            shutil.rmtree(self.log_dir)

    def _logger(self):
        return PlayLogger(self.log_dir)

    def test_jsonl_layout(self):
        lg = self._logger()
        lg.start("测试曲", 120, 3)
        lg.log_note(0, ["mid_1"], ["A"], ok=True, sched_ms=None, actual_ms=None, dev_ms=None)
        lg.log_note(1, ["mid_1", "mid_3"], ["A", "D"], ok=False, sched_ms=100.0, actual_ms=112.0, dev_ms=12.0, error="boom")
        summary = lg.finish(2, 3, error="boom")
        self.assertTrue(os.path.exists(lg.path))
        with open(lg.path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        self.assertEqual([e["type"] for e in lines], ["start", "note", "note", "end"])
        self.assertEqual(lines[0]["score"], "测试曲")
        self.assertEqual(lines[1]["keys"], ["A"])
        self.assertEqual(lines[2]["ok"], False)
        self.assertEqual(lines[2]["error"], "boom")
        self.assertEqual(lines[2]["dev_ms"], 12.0)
        # 统计
        self.assertEqual(summary.logged_notes, 2)
        self.assertEqual(summary.key_failures, 1)
        self.assertEqual(summary.success_rate, 0.5)
        self.assertEqual(summary.avg_dev_ms, 12.0)
        self.assertEqual(summary.max_dev_ms, 12.0)
        self.assertEqual(summary.dev_over_ratio, 1.0)
        self.assertIn("出错: boom", summary.format())

    def test_unique_paths(self):
        lg1 = self._logger()
        lg1.start("a", 100, 1)
        lg2 = self._logger()
        lg2.start("b", 100, 1)
        self.assertNotEqual(lg1.path, lg2.path)
        self.assertTrue(os.path.exists(lg1.path))
        self.assertTrue(os.path.exists(lg2.path))

    def test_degrade_when_dir_unwritable(self):
        # log_dir 路径上是一个文件 → 建目录失败 → 降级为纯内存统计
        blocker = os.path.join(self.log_dir, "blocker")
        os.makedirs(self.log_dir)
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x")
        lg = PlayLogger(blocker)  # 在文件路径下建目录必失败
        lg.start("a", 100, 2)
        lg.log_note(0, ["mid_1"], ["A"], ok=True)
        summary = lg.finish(1, 2)
        self.assertEqual(summary.logged_notes, 1)
        self.assertIsNone(summary.avg_dev_ms)

    def test_dev_over_ratio_threshold(self):
        lg = self._logger()
        lg.start("a", 100, 3)
        lg.log_note(0, ["mid_1"], ["A"], ok=True, sched_ms=100.0, actual_ms=101.0, dev_ms=1.0)
        lg.log_note(1, ["mid_1"], ["A"], ok=True, sched_ms=100.0, actual_ms=90.0, dev_ms=-10.0)
        lg.log_note(2, ["mid_1"], ["A"], ok=True, sched_ms=100.0, actual_ms=130.0, dev_ms=30.0)
        summary = lg.finish(3, 3)
        # |−10| 不超过阈值 10,仅 30 计入
        self.assertEqual(summary.dev_over_ratio, 1 / 3)
        self.assertEqual(summary.avg_dev_ms, (1 + 10 + 30) / 3)


class TestPlayerLogging(unittest.TestCase):
    def setUp(self):
        self.log_dir = os.path.join("data", "test_play_logs_player")
        if os.path.isdir(self.log_dir):
            shutil.rmtree(self.log_dir)

    def tearDown(self):
        if os.path.isdir(self.log_dir):
            shutil.rmtree(self.log_dir)

    def test_integration_summary_and_file(self):
        driver = FakeDriver()
        logger = PlayLogger(self.log_dir)
        player = Player(KeyMap(MAPPING), driver=driver, logger=logger)
        player.play(NOTES, bpm=600, hold_ratio=0.5, gap_ms=0, score_name="集成测试")
        self.assertTrue(wait_done(player))
        summary = player.last_summary
        self.assertIsNotNone(summary)
        self.assertEqual(summary.completed_notes, 3)
        self.assertEqual(summary.logged_notes, 3)
        self.assertEqual(summary.score_name, "集成测试")
        self.assertTrue(os.path.exists(summary.log_path))
        with open(summary.log_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        self.assertEqual(len(lines), 5)  # start + 3 note + end
        self.assertEqual(lines[-1]["completed"], 3)
        # 第二个音符起有间隔偏差记录
        self.assertIsNone(lines[1]["dev_ms"])
        self.assertIsNotNone(lines[2]["dev_ms"])

    def test_no_logger_zero_overhead(self):
        driver = FakeDriver()
        player = Player(KeyMap(MAPPING), driver=driver)
        player.play(NOTES, bpm=600, hold_ratio=0.5, gap_ms=0)
        self.assertTrue(wait_done(player))
        self.assertIsNone(player.last_summary)


if __name__ == "__main__":
    unittest.main()
