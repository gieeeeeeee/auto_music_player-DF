"""统一曲谱数据模型与校验器测试。

运行: python -m unittest tests.test_score_model -v
"""

import os
import unittest

from core.database import ScoreDB
from core.score_model import (
    Chord,
    Note,
    Rest,
    Score,
    ScoreValidationError,
    validate_notes,
)

VALID = [
    {"notes": ["mid_1"], "dur": 1.0},
    {"notes": [], "dur": 0.5},
    {"notes": ["high_1", "high_3"], "dur": 2.0},
]


class TestStorageRoundtrip(unittest.TestCase):
    def test_note_chord_rest(self):
        score = Score.from_storage("测试", 100, VALID)
        self.assertEqual(score.elements[0], Note(1, "mid", 1.0))
        self.assertEqual(score.elements[1], Rest(0.5))
        self.assertEqual(
            score.elements[2],
            Chord((Note(1, "high", 2.0), Note(3, "high", 2.0)), 2.0),
        )
        self.assertEqual(score.to_storage(), VALID)

    def test_invalid_id_raises(self):
        with self.assertRaises(ValueError):
            Score.from_storage("测试", 100, [{"notes": ["high_9"], "dur": 1.0}])

    def test_total_beats(self):
        score = Score.from_storage("测试", 100, VALID)
        self.assertEqual(score.total_beats, 3.5)


class TestValidateNotes(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_notes(VALID), [])
        self.assertEqual(validate_notes(VALID, bpm=120), [])

    def test_invalid_note_ids(self):
        for nid in ("high_8", "mid_0", "bogus", "UPPER_1"):
            errs = validate_notes([{"notes": [nid], "dur": 1.0}])
            self.assertEqual(len(errs), 1, nid)
            self.assertEqual(errs[0].index, 0)
            self.assertIn(nid, str(errs[0]))

    def test_dur_errors(self):
        cases = [
            ({"notes": ["mid_1"], "dur": 0}, "大于 0"),
            ({"notes": ["mid_1"], "dur": -1}, "大于 0"),
            ({"notes": ["mid_1"], "dur": "x"}, "数字"),
            ({"notes": ["mid_1"], "dur": True}, "数字"),
            ({"notes": ["mid_1"], "dur": 32.0}, "超出上限"),
            ({"notes": ["mid_1"]}, "缺少"),
        ]
        for item, keyword in cases:
            errs = validate_notes([item])
            self.assertEqual(len(errs), 1, item)
            self.assertIn(keyword, str(errs[0]))

    def test_structural_errors(self):
        self.assertEqual(validate_notes("notalist")[0].index, -1)
        errs = validate_notes([{"notes": "mid_1", "dur": 1.0}])
        self.assertIn("列表", str(errs[0]))
        errs = validate_notes([{"notes": ["mid_1", 3], "dur": 1.0}])
        self.assertEqual(len(errs), 1)

    def test_error_indexing(self):
        errs = validate_notes(
            [
                {"notes": ["mid_1"], "dur": 1.0},
                {"notes": ["bad"], "dur": 1.0},
                {"notes": [], "dur": 0},
            ]
        )
        self.assertEqual([e.index for e in errs], [1, 2])
        self.assertIn("音符 2", str(errs[0]))
        self.assertIn("音符 3", str(errs[1]))

    def test_bpm(self):
        errs = validate_notes([], bpm=500)
        self.assertEqual(errs[0].index, -1)
        self.assertIn("BPM", str(errs[0]))
        self.assertEqual(validate_notes([], bpm=None), [])


class TestDBValidation(unittest.TestCase):
    def setUp(self):
        self.db = ScoreDB("data/test_score_model.db")

    def tearDown(self):
        self.db.conn.close()
        if os.path.exists("data/test_score_model.db"):
            os.remove("data/test_score_model.db")

    def test_add_rejects_invalid(self):
        with self.assertRaises(ScoreValidationError):
            self.db.add_score("测试", [{"notes": ["bad"], "dur": 1.0}])
        self.assertEqual(len(self.db.list_scores()), 0)

    def test_add_rejects_bad_bpm(self):
        with self.assertRaises(ScoreValidationError):
            self.db.add_score("测试", VALID, bpm_default=999)

    def test_update_rejects_invalid(self):
        sid = self.db.add_score("测试", VALID)
        with self.assertRaises(ScoreValidationError):
            self.db.update_score(sid, "测试", [{"notes": [], "dur": 0}])
        self.assertEqual(self.db.get_score(sid)["notes"], VALID)

    def test_add_accepts_valid(self):
        sid = self.db.add_score("测试", VALID, bpm_default=100)
        self.assertEqual(self.db.get_score(sid)["notes"], VALID)


if __name__ == "__main__":
    unittest.main()
