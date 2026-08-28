"""按键输出自测:验证 scancode 事件真实进入系统输入流。

会真实按下 Q 键约 0.15 秒(全局生效,焦点窗口会收到一个 Q)。
运行: python tests/selftest_input.py
"""

import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

user32 = ctypes.WinDLL("user32")


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def main():
    from core.keyboard_driver import KeyboardDriver, _expected_input_size
    import core.keyboard_driver as kd

    print(f"sizeof(INPUT) = {ctypes.sizeof(kd.INPUT)} (期望 {_expected_input_size()})")
    driver = KeyboardDriver()
    print("driver 初始化 OK")

    vk_q = ord("Q")
    driver.press_key("Q")
    time.sleep(0.15)
    pressed = key_down(vk_q)
    driver.release_key("Q")
    time.sleep(0.1)
    released = not key_down(vk_q)

    print(f"按下 Q 后系统检测到按下: {pressed}")
    print(f"松开 Q 后系统检测到松开: {released}")
    if pressed and released:
        print("自测通过: scancode 按键已真实进入系统输入流")
        return 0
    print("自测失败: 系统未检测到按键")
    return 1


if __name__ == "__main__":
    sys.exit(main())