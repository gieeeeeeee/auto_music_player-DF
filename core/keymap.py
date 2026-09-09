"""音符 -> 输入组合映射。

每个映射项可以是单个键（如 ``A``），也可以是以 ``+`` 连接的鼠标键和
键盘键（如 ``LMB+Q``）。组合会在同一个音符时值内同时按住。
"""

OCTAVES = ("high", "mid", "low")
NOTES = tuple(range(1, 8))


class KeyMap:
    def __init__(self, mapping: dict):
        """mapping: 每个八度包含 7 个输入项，如 ``LMB+Q`` 或 ``A``。"""
        self._mapping = {octave: list(keys) for octave, keys in mapping.items()}
        for octave in OCTAVES:
            if len(self._mapping.get(octave, [])) != 7:
                raise ValueError(f"keymap.{octave} 必须包含 7 个按键")

    def key_for(self, note_id: str) -> str | None:
        """note_id 形如 "high_1" / "mid_3" / "low_5",返回输入组合。"""
        if "_" not in note_id:
            return None
        octave, num = note_id.split("_", 1)
        keys = self._mapping.get(octave)
        if not keys:
            return None
        try:
            idx = int(num) - 1
        except ValueError:
            return None
        if not 0 <= idx < 7:
            return None
        return keys[idx]
