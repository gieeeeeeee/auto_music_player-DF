"""焦点检测模块测试:快照、句柄/标题匹配、fail-open 降级路径(Win32 全部 mock)。

运行: python -m unittest tests.test_window_monitor -v
"""

import sys
import unittest

import core.window_monitor as wm
from core.window_monitor import FocusLockPolicy, ForegroundWatcher


class FakeUser32:
    """user32 替身:GetForegroundWindow 返回可配置句柄,GetWindowTextW 返回预置标题。"""

    def __init__(self, hwnd=0, titles=None):
        self.hwnd = hwnd
        self.titles = titles or {}

    def GetForegroundWindow(self):
        return self.hwnd

    def GetWindowTextW(self, hwnd, buf, n):
        buf.value = self.titles.get(hwnd, "")
        return len(buf.value)


class TestFocusLockPolicy(unittest.TestCase):
    """到达锁定策略:用户切到的首个非本应用窗口成为目标,离开才暂停。"""

    OWN = {"hwnd": 111, "title": "自动演奏器"}
    GAME = {"hwnd": 222, "title": "鸣潮"}
    OTHER = {"hwnd": 333, "title": "记事本"}

    def _policy(self, **kwargs):
        return FocusLockPolicy(**kwargs)

    def test_stays_in_app_does_not_pause_or_lock(self):
        p = self._policy(own_hwnd=111)
        self.assertFalse(p.evaluate(self.OWN))
        self.assertFalse(p.locked)

    def test_first_external_window_locks_without_pause(self):
        p = self._policy(own_hwnd=111)
        self.assertFalse(p.evaluate(self.GAME))
        self.assertTrue(p.locked)
        self.assertEqual(p.target, self.GAME)
        # 留在游戏:不暂停
        self.assertFalse(p.evaluate(self.GAME))

    def test_leave_locked_target_pauses(self):
        p = self._policy(own_hwnd=111)
        p.evaluate(self.GAME)
        self.assertTrue(p.evaluate(self.OTHER))
        self.assertTrue(p.evaluate(self.OWN))    # 切回本应用也算离开游戏
        self.assertTrue(p.evaluate(None))        # 无法判定前台 → 打断

    def test_slow_switch_never_wrongly_pauses(self):
        """用户超过 3 秒才切窗:期间停留本应用不暂停,切到游戏即锁定。"""
        p = self._policy(own_hwnd=111)
        for _ in range(10):
            self.assertFalse(p.evaluate(self.OWN))
        self.assertFalse(p.evaluate(self.GAME))
        self.assertFalse(p.evaluate(self.GAME))
        self.assertTrue(p.evaluate(self.OWN))

    def test_title_override_mode(self):
        p = self._policy(title_override="鸣潮")
        self.assertFalse(p.evaluate(self.GAME))
        self.assertTrue(p.evaluate(self.OTHER))

    def test_hwnd_change_same_title_not_pause(self):
        """游戏全屏切换/重创窗口:句柄变但标题一致 → 不误停,并顺带更新目标句柄。"""
        p = self._policy(own_hwnd=111)
        p.evaluate({"hwnd": 222, "title": "鸣潮"})
        self.assertFalse(p.evaluate({"hwnd": 999, "title": "鸣潮"}))
        self.assertEqual(p.target["hwnd"], 999)
        self.assertTrue(p.evaluate({"hwnd": 123, "title": "桌面"}))   # 标题也变 → 真离开

    def test_fail_open_on_unknown(self):
        p = self._policy(own_hwnd=111)
        self.assertFalse(p.evaluate(None))       # 未锁定时无法判定 → 不打断
        p.evaluate(self.GAME)
        self.assertTrue(p.evaluate(None))        # 锁定后无法判定 → 打断


class TestForegroundWatcher(unittest.TestCase):
    def setUp(self):
        self.watcher = ForegroundWatcher(poll_interval=0.4)

    def tearDown(self):
        wm._user32 = None  # 清理注入,避免影响其他用例

    def _inject(self, **kwargs):
        wm._user32 = FakeUser32(**kwargs)

    # ---------- 快照 ----------

    def test_capture_current(self):
        self._inject(hwnd=4242, titles={4242: "鸣潮"})
        self.assertEqual(self.watcher.capture_current(), {"hwnd": 4242, "title": "鸣潮"})

    def test_capture_none_when_no_foreground(self):
        self._inject(hwnd=0)
        self.assertIsNone(self.watcher.capture_current())

    # ---------- 句柄精确比对 ----------

    def test_target_foreground_by_hwnd(self):
        target = {"hwnd": 4242, "title": "鸣潮"}
        self._inject(hwnd=4242, titles={4242: "鸣潮"})
        self.assertTrue(self.watcher.is_target_foreground(target))
        self._inject(hwnd=999, titles={999: "其他窗口"})
        self.assertFalse(self.watcher.is_target_foreground(target))

    # ---------- 标题子串匹配(优先级最高,大小写不敏感) ----------

    def test_title_override_substring(self):
        self._inject(hwnd=7, titles={7: "鸣潮 - 游戏窗口"})
        self.assertTrue(self.watcher.is_target_foreground({"hwnd": 1}, title_override="鸣潮"))
        self._inject(hwnd=7, titles={7: "Genshin Impact"})
        self.assertTrue(self.watcher.is_target_foreground({"hwnd": 1}, title_override="genshin"))
        self.assertFalse(self.watcher.is_target_foreground({"hwnd": 1}, title_override="原神"))

    # ---------- fail-open:无法判定时不打断演奏 ----------

    def test_fail_open_without_target(self):
        self._inject(hwnd=1)
        self.assertTrue(self.watcher.is_target_foreground(None))

    def test_fail_open_when_no_foreground(self):
        self._inject(hwnd=0)
        self.assertTrue(self.watcher.is_target_foreground({"hwnd": 4242}))

    # ---------- 平台可用性 ----------

    @unittest.skipIf(sys.platform != "win32", "仅 Windows")
    def test_available_on_windows(self):
        self.assertTrue(ForegroundWatcher.is_available())

    @unittest.skipIf(sys.platform == "win32", "非 Windows 平台用例")
    def test_unavailable_off_windows(self):
        self.assertFalse(ForegroundWatcher.is_available())

    @unittest.skipIf(sys.platform != "win32", "真实 API 冒烟(仅 Windows)")
    def test_real_api_smoke(self):
        """不注入替身,验证真实 Win32 原型绑定与调用无异常。"""
        snapshot = self.watcher.capture_current()
        self.assertTrue(snapshot is None or isinstance(snapshot, dict))
        result = self.watcher.is_target_foreground(snapshot)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
