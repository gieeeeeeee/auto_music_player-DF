"""简谱解析器:规范化简谱文本 -> 结构化音符序列。

输出协议(与大模型 prompt 一致):
- 音高:1-7 中音;数字+' 高音;数字+, 低音;0 休止
- 时值:无后缀=四分音符(1拍);_ = 八分(0.5拍), __ = 十六分(0.25拍);
  - = 二分(2拍), -- = 全音符(4拍);附点用 . 或 · 跟在时值符号后,时值 ×1.5
- 和弦:[音1 音2 ...]时值后缀,如 [1' 3' 5']- ;和弦内部只写音高
- 小节线 | ‖ 、调号行(1=C)、歌词行自动忽略

输出: [{ "notes": ["high_1"], "dur": 0.5 }, ...]
dur 单位为拍;休止符 notes 为空列表。
"""

import re

_PITCH_SUFFIX = {"'": "high", ",": "low"}
_CHORD_RE = re.compile(r"[\[\(]([^\]\)]+)[\]\)]([_\-.·]*)")
_NOTE_RE = re.compile(r"[0-7](?:'|,|\.|·|_|-)*")
_TUNE_LINE_RE = re.compile(r"^\s*1\s*=\s*[A-Ga-g]")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def _split_pitch_dur(suffix: str):
    """把数字后的修饰符串拆成(音高, 时值部分)。"""
    pitch = "mid"
    rest = suffix
    if rest.startswith(("'", ",")):
        pitch = _PITCH_SUFFIX[rest[0]]
        rest = rest[1:]
    elif rest.startswith("·"):
        # · 是明确的附点符号,始终作为附点
        pass
    elif rest.startswith("."):
        # 容错:单独的 . 且后面没有时值符号时,视为低音
        if len(rest) == 1 or rest[1] not in "_-.·":
            pitch = "low"
            rest = rest[1:]
    return pitch, rest


def _parse_dur(rest: str) -> float:
    dur = 1.0
    dotted = False
    for ch in rest:
        if ch == "_":
            dur *= 0.5
        elif ch == "-":
            dur *= 2.0
        elif ch in ".·":
            dotted = True
    if dotted:
        dur *= 1.5
    return dur


def _note_id(num: int, pitch: str) -> str:
    return f"{pitch}_{num}"


def _build_single(token: str):
    num = int(token[0])
    pitch, rest = _split_pitch_dur(token[1:])
    dur = _parse_dur(rest)
    if num == 0:
        return {"notes": [], "dur": dur}
    if not 1 <= num <= 7:
        return None
    return {"notes": [_note_id(num, pitch)], "dur": dur}


def _build_chord(inner: str, suffix: str):
    dur = _parse_dur(suffix)
    note_ids = []
    for part in re.split(r"[,\s]+", inner.strip()):
        m = _NOTE_RE.match(part)
        if not m:
            continue
        token = m.group(0)
        num = int(token[0])
        if num == 0 or not 1 <= num <= 7:
            continue
        pitch, _ = _split_pitch_dur(token[1:])
        note_ids.append(_note_id(num, pitch))
    return {"notes": note_ids, "dur": dur}


def _is_lyric_line(line: str) -> bool:
    """歌词行:中文字符明显多于数字,跳过。"""
    chinese = len(_CHINESE_RE.findall(line))
    digits = len(re.findall(r"[0-7]", line))
    return chinese > digits


def _clean_lines(text: str):
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _TUNE_LINE_RE.match(line) or _is_lyric_line(line):
            continue
        line = line.replace("|", " ").replace("‖", " ")
        yield line


def parse_jianpu(text: str) -> list[dict]:
    """解析规范化简谱文本,返回音符序列列表。"""
    result = []
    for line in _clean_lines(text):
        chord_matches = list(_CHORD_RE.finditer(line))
        single_scan = _CHORD_RE.sub(" ", line)
        for m in _NOTE_RE.finditer(single_scan):
            note = _build_single(m.group(0))
            if note is not None:
                result.append(note)
        for cm in chord_matches:
            note = _build_chord(cm.group(1), cm.group(2))
            if note["notes"]:
                result.append(note)
    return result