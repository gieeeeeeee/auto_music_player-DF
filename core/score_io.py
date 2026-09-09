"""曲谱导入导出:JSON(完整数据)与 MIDI(Type 0/1 单轨旋律)。

- JSON:自带 format/version 信封;导入与入库走同一 Schema 校验器,非法数据直接拒绝
- MIDI:零依赖手写解析(标准 MThd/MTrk/VLQ/running status),
  只支持 Type 0/1 与 ticks 时基;SMPTE / Type 2 明确拒绝并给出可读提示
  - 黑键(半音)与 low/mid/high 三个八度(C3~B5)之外的音符无法映射 21 键简谱,
    跳过后对应位置以休止占位(保持后续节奏对齐),并计入警告
  - 时值取"相邻音符组起始间隔"(与简谱节奏槽一致);
    持续音跨越后续音符会折断为多次触发(简谱格式的固有限制)
  - 休止符在 MIDI 中天然表现为音符间隙,导入后并入前一音符的时值槽
- 统一入口 import_any() 按扩展名分发;若未来引入第三方 MIDI 库,只需替换 import_midi 内部实现
"""

import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field

from core.score_model import require_valid

JSON_FORMAT = "auto-music-player-score"
JSON_VERSION = 1
TPQ = 480          # 导出用的每四分音符 tick 数
MIN_BPM, MAX_BPM = 30, 300
MAX_DUR = 16.0     # 与校验器上限一致

_OCTAVE_OFFSET = {"low": -12, "mid": 0, "high": 12}
_NUM_SEMITONE = (0, 2, 4, 5, 7, 9, 11)   # 简谱 1-7 = C D E F G A B(自然音级,非半音递增)
_WHITE_NUM = {0: 1, 2: 2, 4: 3, 5: 4, 7: 5, 9: 6, 11: 7}
_BLACK_PCS = {1, 3, 6, 8, 10}
_MIDI_MIN, _MIDI_MAX = 48, 83   # low_1(C3) .. high_7(B5)


@dataclass
class ImportResult:
    name: str
    bpm: int
    notes: list
    warnings: list = field(default_factory=list)
    kind: str = ""   # "json" | "midi"


class MidiParseError(ValueError):
    pass


# ---------- 音符映射 ----------

def note_id_to_midi(note_id: str) -> int:
    """note_id(如 mid_1)→ MIDI 音高编号;C4(中音 1)= 60。非法 id 抛 ValueError。"""
    octave, sep, num = note_id.partition("_")
    if octave not in _OCTAVE_OFFSET or not sep or not num.isdigit() or not 1 <= int(num) <= 7:
        raise ValueError(f"无效音符: {note_id}(应为 high/mid/low_1~7)")
    return 60 + _OCTAVE_OFFSET[octave] + _NUM_SEMITONE[int(num) - 1]


def midi_to_note_id(midi: int) -> str | None:
    """MIDI 音高 → note_id;黑键或 C3~B5 之外返回 None。"""
    if not _MIDI_MIN <= midi <= _MIDI_MAX:
        return None
    pc = midi % 12
    if pc in _BLACK_PCS:
        return None
    octave = ("low", "mid", "high")[midi // 12 - 4]
    return f"{octave}_{_WHITE_NUM[pc]}"


# ---------- JSON ----------

def export_json(path: str, score: dict) -> None:
    data = {
        "format": JSON_FORMAT,
        "version": JSON_VERSION,
        "name": score.get("name", ""),
        "bpm": int(score.get("bpm_default", 100)),
        "notes": score.get("notes", []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def import_json(path: str) -> ImportResult:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    stem = os.path.splitext(os.path.basename(path))[0]
    if isinstance(data, list):
        notes, name, bpm = data, stem, 100
    elif isinstance(data, dict) and isinstance(data.get("notes"), list):
        notes = data["notes"]
        name = str(data.get("name") or stem)
        try:
            bpm = int(data.get("bpm", 100))
        except (TypeError, ValueError):
            raise ValueError("JSON 中的 bpm 不是有效数字")
    else:
        raise ValueError("JSON 结构不符合乐谱导出格式(需要 name/bpm/notes 或 notes 列表)")
    require_valid(notes, bpm=bpm)   # 导入与入库同一校验器
    return ImportResult(name=name, bpm=bpm, notes=notes, kind="json")


# ---------- MIDI 基础编码 ----------

def _vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("负的 delta time")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    out.reverse()
    return bytes(out)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + len(payload).to_bytes(4, "big") + payload


def _read_vlq(data: bytes, pos: int):
    value = 0
    n = len(data)
    for _ in range(4):
        if pos >= n:
            raise MidiParseError("MIDI 文件数据不完整(VLQ 越界)")
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos
    raise MidiParseError("MIDI VLQ 长度异常(超过 4 字节)")


# ---------- MIDI 导出(Type 0) ----------

def export_midi(path: str, score: dict) -> None:
    bpm = max(1, int(score.get("bpm_default", 100)))
    track = bytearray()
    name = str(score.get("name", ""))[:120]
    if name:
        nb = name.encode("utf-8")
        track += _vlq(0) + b"\xff\x03" + _vlq(len(nb)) + nb
    tempo = 60_000_000 // bpm
    track += _vlq(0) + b"\xff\x51\x03" + tempo.to_bytes(3, "big")

    events = []   # (tick, priority, bytes);同 tick 时 note-off 先于 note-on
    tick = 0
    for el in score.get("notes", []):
        dur_ticks = max(1, round(el["dur"] * TPQ))
        for m in sorted({note_id_to_midi(nid) for nid in el["notes"]}):
            events.append((tick, 1, bytes((0x90, m, 100))))
            events.append((tick + dur_ticks, 0, bytes((0x80, m, 0))))
        tick += dur_ticks
    events.sort(key=lambda e: (e[0], e[1]))
    prev = 0
    for t, _, payload in events:
        track += _vlq(t - prev) + payload
        prev = t
    track += _vlq(0) + b"\xff\x2f\x00"   # 轨道结束(meta 事件同样需要前置 delta)

    header = (
        b"MThd" + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")      # format 0
        + (1).to_bytes(2, "big")      # 单轨
        + TPQ.to_bytes(2, "big")
    )
    with open(path, "wb") as f:
        f.write(header + _chunk(b"MTrk", bytes(track)))


# ---------- MIDI 导入(Type 0/1) ----------

def _split_chunks(raw: bytes):
    if len(raw) < 14 or raw[:4] != b"MThd":
        raise MidiParseError("不是有效的 MIDI 文件(缺少 MThd 头)")
    hdr_len = int.from_bytes(raw[4:8], "big")
    fmt = int.from_bytes(raw[8:10], "big")
    ntrks = int.from_bytes(raw[10:12], "big")
    division = int.from_bytes(raw[12:14], "big")
    if fmt == 2:
        raise MidiParseError("暂不支持 Type 2(异步轨)MIDI 文件,请用乐谱软件另存为 Type 0/1")
    if division & 0x8000:
        raise MidiParseError("暂不支持 SMPTE 时基的 MIDI 文件,请用乐谱软件转换为标准 ticks 时基")
    tpq = division if division > 0 else 480
    pos = 8 + hdr_len
    tracks = []
    for _ in range(ntrks):
        if pos + 8 > len(raw):
            break
        tag = raw[pos:pos + 4]
        length = int.from_bytes(raw[pos + 4:pos + 8], "big")
        pos += 8
        if tag == b"MTrk":
            tracks.append(raw[pos:pos + length])
        pos += length
    if not tracks:
        raise MidiParseError("MIDI 文件中没有轨道数据")
    return tpq, tracks


def _parse_track(tdata: bytes, tpq: int):
    """解析单轨,返回 (groups{tick:{pitch:off}}, bpm, 打击乐数, 未闭合数)。"""
    pos, tick, end_tick = 0, 0, 0
    running = None
    bpm = None
    perc = 0
    note_events = []   # (tick, is_on, channel, pitch) 按时间序
    n = len(tdata)
    while pos < n:
        delta, pos = _read_vlq(tdata, pos)
        tick += delta
        if pos >= n:
            break
        b = tdata[pos]
        if b == 0xFF:   # meta 事件
            pos += 1
            if pos >= n:
                raise MidiParseError("MIDI 文件数据不完整(meta 事件)")
            mtype = tdata[pos]
            pos += 1
            length, pos = _read_vlq(tdata, pos)
            if pos + length > n:
                raise MidiParseError("MIDI 文件数据不完整(meta 载荷)")
            payload = tdata[pos:pos + length]
            pos += length
            if mtype == 0x51 and len(payload) == 3 and bpm is None:
                tempo_us = int.from_bytes(payload, "big")
                if tempo_us > 0:
                    bpm = round(60_000_000 / tempo_us)
            elif mtype == 0x2F:
                end_tick = max(end_tick, tick)
                break   # 轨道结束
            running = None
        elif b in (0xF0, 0xF7):   # sysex:按长度跳过
            pos += 1
            length, pos = _read_vlq(tdata, pos)
            if pos + length > n:
                raise MidiParseError("MIDI 文件数据不完整(sysex)")
            pos += length
            running = None
        else:
            if b & 0x80:
                status = b
                pos += 1
            else:
                if running is None:
                    raise MidiParseError("MIDI 文件数据不完整(无效的 running status)")
                status = running
            running = status
            kind = status & 0xF0
            channel = status & 0x0F
            n_data = 1 if kind in (0xC0, 0xD0) else 2
            if pos + n_data > n:
                raise MidiParseError("MIDI 文件数据不完整(通道事件)")
            d1 = tdata[pos]
            d2 = tdata[pos + 1] if n_data == 2 else 0
            pos += n_data
            if kind == 0x90 and d2 > 0:
                if channel == 9:
                    perc += 1
                else:
                    note_events.append((tick, True, channel, d1))
            elif kind == 0x80 or (kind == 0x90 and d2 == 0):
                if channel == 9:
                    perc += 1
                else:
                    note_events.append((tick, False, channel, d1))
        end_tick = max(end_tick, tick)

    # 同通道同音高 FIFO 配对;未闭合的按轨道结尾闭合
    open_notes = defaultdict(deque)
    sounding = []
    unclosed = 0
    for t, is_on, ch, pitch in note_events:
        key = (ch, pitch)
        if is_on:
            open_notes[key].append(t)
        elif open_notes[key]:
            sounding.append((open_notes[key].popleft(), t, pitch))
    for key, dq in open_notes.items():
        for on_t in dq:
            sounding.append((on_t, max(end_tick, on_t + tpq), key[1]))
            unclosed += 1

    groups = defaultdict(dict)   # tick -> {pitch: off_tick}
    for on_t, off_t, pitch in sounding:
        if off_t > groups[on_t].get(pitch, -1):
            groups[on_t][pitch] = off_t
    return groups, bpm, perc, unclosed


def import_midi(path: str) -> ImportResult:
    with open(path, "rb") as f:
        raw = f.read()
    tpq, tracks = _split_chunks(raw)
    groups = defaultdict(dict)
    bpm = None
    warnings = []
    perc = unclosed = 0
    for tdata in tracks:
        t_groups, t_bpm, t_perc, t_unclosed = _parse_track(tdata, tpq)
        perc += t_perc
        unclosed += t_unclosed
        if bpm is None and t_bpm:
            bpm = t_bpm
        for t, pitches in t_groups.items():
            slot = groups[t]
            for pitch, off in pitches.items():
                if off > slot.get(pitch, -1):
                    slot[pitch] = off

    ticks = sorted(groups)
    elements = []
    black = out_of_range = 0
    for i, t in enumerate(ticks):
        next_t = ticks[i + 1] if i + 1 < len(ticks) else None
        ids = []
        for pitch in sorted(groups[t]):
            nid = midi_to_note_id(pitch)
            if nid is None:
                if _MIDI_MIN <= pitch <= _MIDI_MAX:
                    black += 1
                else:
                    out_of_range += 1
            else:
                ids.append(nid)
        if next_t is not None:
            dur = (next_t - t) / tpq
        else:
            dur = max(0.25, (max(groups[t].values()) - t) / tpq)
        elements.append({"notes": ids, "dur": round(min(dur, MAX_DUR), 6)})

    if black:
        warnings.append(f"已跳过 {black} 个黑键音符(简谱无法表示),对应位置以休止占位")
    if out_of_range:
        warnings.append(f"已跳过 {out_of_range} 个八度范围外音符(C3~B5 之外),对应位置以休止占位")
    if perc:
        warnings.append(f"已忽略 {perc} 个打击乐通道音符")
    if unclosed:
        warnings.append(f"{unclosed} 个未结束音符已按轨道结尾闭合")

    if bpm is None:
        bpm = 100
    else:
        clamped = min(MAX_BPM, max(MIN_BPM, bpm))
        if clamped != bpm:
            warnings.append(f"MIDI 速度 {bpm} BPM 超出支持范围,已调整为 {clamped}")
        bpm = clamped

    name = os.path.splitext(os.path.basename(path))[0]
    require_valid(elements, bpm=bpm)   # 导入与入库同一校验器
    return ImportResult(name=name, bpm=bpm, notes=elements, warnings=warnings, kind="midi")


# ---------- 统一入口 ----------

def import_any(path: str) -> ImportResult:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return import_json(path)
    if ext in (".mid", ".midi"):
        return import_midi(path)
    raise ValueError(f"不支持的导入格式: {ext}(支持 .json / .mid / .midi)")
