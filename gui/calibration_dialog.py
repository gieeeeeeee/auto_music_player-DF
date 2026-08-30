"""延迟校准向导对话框:采样 → 结果展示 → 应用写回 config.yaml。

校准在后台线程执行(约 4 秒),测试按键会发送到当前前台窗口;
结果可应用于当前演奏会话(立即生效)并写入配置(重启后仍有效)。
"""

import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.latency_calibration import LatencyCalibrator
from gui.theme import BRAND, INK, INK_2, LINE_2, SURFACE
from gui.widgets import AppDialog


def update_player_config_value(path: str, key: str, value):
    """手术式更新 config.yaml 中 player 段的指定键,保留全部注释与编码。

    键已存在则原位替换;不存在则插入到 player: 行之后。
    """
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    in_player = False
    done = False
    for line in lines:
        s = line.rstrip("\n")
        top = bool(s) and not s[0].isspace()
        if top:
            in_player = s.startswith("player:")
        if in_player and not done and s.strip().startswith(f"{key}:"):
            indent = s[: len(s) - len(s.lstrip())]
            out.append(f"{indent}{key}: {value}\n")
            done = True
            continue
        out.append(line)
    if not done:
        for idx, line in enumerate(out):
            if line.rstrip("\n").startswith("player:"):
                out.insert(idx + 1, f"  # 系统输出延迟补偿(毫秒,延迟校准向导写入)\n  {key}: {value}\n")
                done = True
                break
    if not done:
        out.append("player:\n")
        out.append(f"  {key}: {value}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


class CalibrationDialog(QDialog):
    sample_tick = pyqtSignal(int)
    calib_done = pyqtSignal(object)

    def __init__(self, parent, player, config_path=None):
        super().__init__(parent)
        self._player = player
        self._config_path = config_path
        self._stop = threading.Event()
        self._thread = None
        self._result = None
        self.setWindowTitle("延迟校准")
        self.setModal(True)
        self.setFixedWidth(480)
        self._build()

    def _card(self):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {LINE_2}; border-radius: 12px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        return frame, lay

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        card, lay = self._card()
        title = QLabel("演奏输出延迟校准")
        title.setStyleSheet(f"color: {INK}; font-size: 15px; font-weight: 600;")
        lay.addWidget(title)
        desc = QLabel(
            "将按固定节奏发送 16 次测试按键(中音 1/2 交替,约 4 秒)。\n"
            "校准测量的是本机输出链路的调度滞后(不含游戏响应),\n"
            "补偿值用于抵消每次发送的系统性滞后,消除长曲演奏的节奏漂移。\n"
            "注意:测试按键将发送到当前前台窗口。"
        )
        desc.setStyleSheet(f"color: {INK_2}; font-size: 12px;")
        lay.addWidget(desc)
        root.addWidget(card)

        card2, lay2 = self._card()
        self.progress = QProgressBar()
        self.progress.setRange(0, 16)
        self.progress.setValue(0)
        lay2.addWidget(self.progress)
        self.result_label = QLabel("点击「开始校准」后请勿操作键盘鼠标。")
        self.result_label.setStyleSheet(f"color: {INK_2}; font-size: 12px; font-family: Consolas;")
        lay2.addWidget(self.result_label)
        root.addWidget(card2, 1)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始校准")
        self.start_btn.setObjectName("BtnPrimary")
        self.start_btn.clicked.connect(self._start)
        self.apply_btn = QPushButton("应用并保存")
        self.apply_btn.setObjectName("BtnPrimary")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("BtnSecondary")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.apply_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self.sample_tick.connect(self._on_sample)
        self.calib_done.connect(self._on_done)

    def _start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._result = None
        self.apply_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.result_label.setText("校准中...")
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        calibrator = LatencyCalibrator(self._player.driver, self._player.keymap)
        result = calibrator.run(self._stop, on_sample=lambda k: self.sample_tick.emit(k))
        self.calib_done.emit(result)

    def _on_sample(self, count):
        self.progress.setValue(count)

    def _on_done(self, result):
        self._result = result
        self.start_btn.setEnabled(True)
        self.result_label.setText(result.format())
        if result.samples > 0 and not result.cancelled:
            self.apply_btn.setEnabled(True)

    def _apply(self):
        if self._result is None or self._result.samples == 0:
            return
        value = self._result.compensation_ms
        self._player.latency_compensation_ms = value
        note = f"延迟补偿已设为 {value}ms,对下一次演奏立即生效。"
        if self._config_path:
            try:
                update_player_config_value(self._config_path, "latency_compensation_ms", value)
                note += "\n已写入 config.yaml,重启后依然有效。"
            except OSError as e:
                AppDialog.show_error(self, "写入配置失败", str(e))
                return
        AppDialog.show_success(self, "已应用", note)

    def closeEvent(self, event):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(1.0)
        super().closeEvent(event)
