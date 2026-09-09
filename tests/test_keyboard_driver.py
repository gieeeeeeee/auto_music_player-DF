"""组合鼠标/键盘输入的纯逻辑测试。"""

import unittest
from unittest.mock import patch

from core.keyboard_driver import KeyboardDriver


class TestKeyboardDriver(unittest.TestCase):
    def test_expand_combined_inputs_and_deduplicate_mouse_button(self):
        self.assertEqual(
            KeyboardDriver._expand_inputs(["LMB+Q", "LMB+W", "A"]),
            ["LMB", "Q", "W", "A"],
        )

    def test_expand_accepts_mouse_aliases(self):
        self.assertEqual(
            KeyboardDriver._expand_inputs(["mouse_left+q", "RMB+Z"]),
            ["MOUSE_LEFT", "Q", "RMB", "Z"],
        )

    def test_combination_is_pressed_and_released_in_safe_order(self):
        driver = object.__new__(KeyboardDriver)
        with patch.object(KeyboardDriver, "_send") as send:
            driver.press_key("LMB+Q")
            driver.release_key("LMB+Q")
        self.assertEqual(
            [(call.args[0], call.kwargs["up"]) for call in send.call_args_list],
            [("LMB", False), ("Q", False), ("Q", True), ("LMB", True)],
        )


if __name__ == "__main__":
    unittest.main()
