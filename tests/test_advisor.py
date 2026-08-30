"""AI 编谱建议测试:输出拆分容错、非法记号过滤、注入式调用(不触网)。

运行: python -m unittest tests.test_advisor -v
"""

import unittest

from core.advisor import ADVISOR_PROMPT, AdvisorResult, generate_advice, parse_advice_response

WELL_FORMED = """JIANPU:
1 2 3_ 3_ 5- 0 [1' 3' 5']-
TIPS:
节奏先慢后快
结尾落在高音上
和弦只在句尾使用
"""

MISSING_FORMAT = """这是一段欢快的旋律:
1 2 3 5, 6 5' 3 1
希望对你有帮助"""


class TestParseAdvice(unittest.TestCase):
    def test_well_formed(self):
        r = parse_advice_response(WELL_FORMED)
        self.assertTrue(r.ok)
        self.assertEqual(r.jianpu_text, "1 2 3_ 3_ 5- 0 [1' 3' 5']-")
        self.assertEqual(r.tips, ["节奏先慢后快", "结尾落在高音上", "和弦只在句尾使用"])
        self.assertEqual(r.warnings, [])

    def test_missing_format_fallback(self):
        r = parse_advice_response(MISSING_FORMAT)
        self.assertTrue(r.ok)
        # jianpu_text 保留模型原文;中文说明行在解析时被当歌词跳过,音符仍可提取
        self.assertIn("1 2 3 5, 6 5' 3 1", r.jianpu_text)
        self.assertTrue(any("未按" in w for w in r.warnings))

    def test_invalid_tokens_kept_with_warning(self):
        """原文保留(用户可编辑),非法记号通过警告提示。"""
        r = parse_advice_response("JIANPU:\n1 8 @ 2\nTIPS:\n建议\n")
        self.assertEqual(r.jianpu_text, "1 8 @ 2")
        self.assertTrue(r.ok)
        self.assertTrue(any("无法识别" in w for w in r.warnings))

    def test_empty_output(self):
        r = parse_advice_response("抱歉,我无法完成该请求。")
        self.assertFalse(r.ok)
        self.assertTrue(any("未能" in w for w in r.warnings))

    def test_tips_capped(self):
        raw = "JIANPU:\n1\nTIPS:\n" + "\n".join(f"建议{i}" for i in range(10))
        r = parse_advice_response(raw)
        self.assertEqual(len(r.tips), 5)


class TestGenerateAdvice(unittest.TestCase):
    def test_uses_injected_chat_and_prompt(self):
        captured = {}

        def fake_chat(api_base, api_key, model, prompt, timeout):
            captured.update(base=api_base, key=api_key, model=model, prompt=prompt)
            return WELL_FORMED

        r = generate_advice(
            "一段欢快旋律", "https://api.example.com/v1", "sk-test", "text-model",
            chat_fn=fake_chat,
        )
        self.assertTrue(r.ok)
        self.assertEqual(captured["base"], "https://api.example.com/v1")
        self.assertEqual(captured["key"], "sk-test")
        self.assertEqual(captured["model"], "text-model")
        self.assertIn("一段欢快旋律", captured["prompt"])
        self.assertNotIn("{desc}", captured["prompt"])
        self.assertIn("21 个琴键", captured["prompt"])   # 协议规则随提示词注入

    def test_empty_desc_rejected_before_network(self):
        called = []

        def fake_chat(*args, **kwargs):
            called.append(1)
            return WELL_FORMED

        with self.assertRaises(ValueError):
            generate_advice("   ", "b", "k", "m", chat_fn=fake_chat)
        self.assertEqual(called, [])   # 未触网

    def test_network_error_propagates(self):
        def fake_chat(*args, **kwargs):
            raise RuntimeError("网络错误: boom")

        with self.assertRaises(RuntimeError):
            generate_advice("desc", "b", "k", "m", chat_fn=fake_chat)


class TestAdvisorResultContract(unittest.TestCase):
    def test_default_not_ok(self):
        self.assertFalse(AdvisorResult().ok)

    def test_prompt_has_desc_placeholder(self):
        self.assertIn("{desc}", ADVISOR_PROMPT)


if __name__ == "__main__":
    unittest.main()
