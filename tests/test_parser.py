"""解析器单元测试。运行: python -m unittest tests.test_parser -v"""

import unittest

from core.parser import parse_jianpu


class TestParser(unittest.TestCase):
    def test_basic_mid(self):
        r = parse_jianpu("1 2 3 4 5 6 7")
        self.assertEqual(
            r,
            [
                {"notes": ["mid_1"], "dur": 1.0},
                {"notes": ["mid_2"], "dur": 1.0},
                {"notes": ["mid_3"], "dur": 1.0},
                {"notes": ["mid_4"], "dur": 1.0},
                {"notes": ["mid_5"], "dur": 1.0},
                {"notes": ["mid_6"], "dur": 1.0},
                {"notes": ["mid_7"], "dur": 1.0},
            ],
        )

    def test_octaves(self):
        r = parse_jianpu("1' 2' 3, 4,")
        self.assertEqual(
            [n["notes"][0] for n in r],
            ["high_1", "high_2", "low_3", "low_4"],
        )

    def test_durations(self):
        r = parse_jianpu("5- 3_ 1__ 7--")
        self.assertEqual([n["dur"] for n in r], [2.0, 0.5, 0.25, 4.0])

    def test_dotted(self):
        r = parse_jianpu("5_· 1·")
        self.assertEqual([(n["notes"], n["dur"]) for n in r],
                         [(["mid_5"], 0.75), (["mid_1"], 1.5)])

    def test_chord(self):
        r = parse_jianpu("[1' 3' 5']-")
        self.assertEqual(r, [{"notes": ["high_1", "high_3", "high_5"], "dur": 2.0}])

    def test_rest(self):
        r = parse_jianpu("0 0_ 0--")
        self.assertEqual([n["dur"] for n in r], [1.0, 0.5, 4.0])
        self.assertTrue(all(n["notes"] == [] for n in r))

    def test_barline_and_tune_line(self):
        r = parse_jianpu("1=C 4/4\n1 | 2 ‖ 3")
        self.assertEqual([n["notes"][0] for n in r], ["mid_1", "mid_2", "mid_3"])

    def test_lyric_line_skipped(self):
        r = parse_jianpu("一闪一闪亮晶晶\n1 1 5 5 6 6 5-")
        self.assertEqual(len(r), 7)

    def test_dot_as_low_fallback(self):
        r = parse_jianpu("5. 6.")
        self.assertEqual([n["notes"][0] for n in r], ["low_5", "low_6"])

    def test_sample(self):
        from core.recognizer import SAMPLE_JIANPU

        r = parse_jianpu(SAMPLE_JIANPU)
        self.assertEqual(len(r), 23)
        self.assertIn({"notes": ["high_5"], "dur": 2.0}, r)
        self.assertIn({"notes": ["high_1", "high_3", "high_5"], "dur": 2.0}, r)
        self.assertIn({"notes": ["low_5"], "dur": 1.0}, r)


if __name__ == "__main__":
    unittest.main()