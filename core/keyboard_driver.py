"""键盘/鼠标模拟驱动:Windows SendInput + scancode。

- KEYEVENTF_SCANCODE 方式发送物理扫描码,兼容 DirectInput / Raw Input 游戏
- INPUT 结构体与 winuser.h 完全一致(x64 下 sizeof=40),否则 SendInput 静默失败
- 发送失败时抛出异常,不静默吞掉
"""

import ctypes
import sys
import time

INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MAPVK_VK_TO_VSC = 0

ULONG_PTR = ctypes.c_size_t

_user32 = None


def _load_user32():
    """延迟加载 user32:保证本模块在非 Windows 平台可安全导入(便于测试隔离)。"""
    global _user32
    if _user32 is None:
        if sys.platform != "win32":
            raise OSError("KeyboardDriver 仅支持 Windows(SendInput)")
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
    return _user32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTunion)]


def _expected_input_size() -> int:
    return 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28


class KeyboardDriver:
    """发送键盘键及 ``LMB+Q`` / ``RMB+Z`` 形式的鼠标-键盘组合。"""

    CHORD_INTERVAL_MS = 5  # 和弦键之间的发送间隔,保证游戏按序收到

    def __init__(self):
        size = ctypes.sizeof(INPUT)
        if size != _expected_input_size():
            raise RuntimeError(
                f"INPUT 结构体大小异常: {size} != {_expected_input_size()},SendInput 将不可用"
            )

    def press_key(self, key: str):
        for part in self._expand_inputs([key]):
            self._send(part, up=False)

    def release_key(self, key: str):
        for part in reversed(self._expand_inputs([key])):
            self._send(part, up=True)

    def press_chord(self, keys: list[str]):
        for i, k in enumerate(self._expand_inputs(keys)):
            if i:
                time.sleep(self.CHORD_INTERVAL_MS / 1000.0)
            self._send(k, up=False)

    def release_chord(self, keys: list[str]):
        # 与按下相反的顺序释放，确保组合键的键盘部分先于鼠标键松开。
        for i, k in enumerate(reversed(self._expand_inputs(keys))):
            if i:
                time.sleep(self.CHORD_INTERVAL_MS / 1000.0)
            self._send(k, up=True)

    @staticmethod
    def _expand_inputs(keys: list[str]) -> list[str]:
        """展开组合并去重，避免和弦中的多个高音重复按下同一个鼠标键。"""
        result = []
        for key in keys:
            for part in str(key).upper().split("+"):
                part = part.strip()
                if part and part not in result:
                    result.append(part)
        return result

    @classmethod
    def _scan_code(cls, key: str) -> int:
        u32 = _load_user32()
        ch = key.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            vk = ord(ch)
        else:
            vk = u32.VkKeyScanW(ord(ch[0])) & 0xFF
        return u32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)

    @classmethod
    def _send(cls, key: str, up: bool):
        mouse_flags = {
            "LMB": (MOUSEEVENTF_LEFTUP if up else MOUSEEVENTF_LEFTDOWN),
            "RMB": (MOUSEEVENTF_RIGHTUP if up else MOUSEEVENTF_RIGHTDOWN),
            "MOUSE_LEFT": (MOUSEEVENTF_LEFTUP if up else MOUSEEVENTF_LEFTDOWN),
            "MOUSE_RIGHT": (MOUSEEVENTF_RIGHTUP if up else MOUSEEVENTF_RIGHTDOWN),
        }
        u32 = _load_user32()
        mouse_flag = mouse_flags.get(key.upper())
        if mouse_flag is not None:
            inp = INPUT(type=INPUT_MOUSE)
            inp.mi = MOUSEINPUT(0, 0, 0, mouse_flag, 0, 0)
            sent = u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            if sent != 1:
                raise OSError(f"SendInput 发送失败(mouse={key}, winerror={ctypes.GetLastError()})")
            return
        scan = cls._scan_code(key)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        sent = u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            raise OSError(f"SendInput 发送失败(key={key}, winerror={ctypes.GetLastError()})")
