"""键盘模拟驱动:Windows SendInput + scancode。

- KEYEVENTF_SCANCODE 方式发送物理扫描码,兼容 DirectInput / Raw Input 游戏
- INPUT 结构体与 winuser.h 完全一致(x64 下 sizeof=40),否则 SendInput 静默失败
- 发送失败时抛出异常,不静默吞掉
"""

import ctypes
import sys
import time

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
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
    """接口与 pynput 版保持一致:press/release 单键与和弦。"""

    CHORD_INTERVAL_MS = 5  # 和弦键之间的发送间隔,保证游戏按序收到

    def __init__(self):
        size = ctypes.sizeof(INPUT)
        if size != _expected_input_size():
            raise RuntimeError(
                f"INPUT 结构体大小异常: {size} != {_expected_input_size()},SendInput 将不可用"
            )

    def press_key(self, key: str):
        self._send(key, up=False)

    def release_key(self, key: str):
        self._send(key, up=True)

    def press_chord(self, keys: list[str]):
        for i, k in enumerate(keys):
            if i:
                time.sleep(self.CHORD_INTERVAL_MS / 1000.0)
            self._send(k, up=False)

    def release_chord(self, keys: list[str]):
        for i, k in enumerate(keys):
            if i:
                time.sleep(self.CHORD_INTERVAL_MS / 1000.0)
            self._send(k, up=True)

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
        u32 = _load_user32()
        scan = cls._scan_code(key)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        sent = u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            raise OSError(f"SendInput 发送失败(key={key}, winerror={ctypes.GetLastError()})")