"""演奏控制页(对齐 Web 设计稿):选谱 -> BPM -> 开始/停止/重置 -> 进度。

三态控制:开始(或暂停后"继续演奏") / 停止(= 暂停,进度保留) / 重置(仅停止后可用,进度归零)。
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.theme import BRAND, INK_2, INK_3, STATE_INFO
from gui.widgets import AppDialog


class PlayerTab(QWidget):
    def __init__(self, db, player, player_cfg):
        super().__init__()
        self._db = db
        self._player = player
        self._hold_ratio = float(player_cfg.get("hold_ratio", 0.75))
        self._gap_ms = float(player_cfg.get("gap_ms", 20))
        self._score_id = None
        self._had_error = False
        self._paused_done = 0
        self._paused_total = 0
        self._build_ui()
        self._player.progress.connect(self._on_progress)
        self._player.finished.connect(self._on_finished)
        self._player.paused.connect(self._on_paused)
        self._player.error_occurred.connect(self._on_error)

    def _card(self, title):
        card = QFrame()
        card.setObjectName("SectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        t = QLabel(title)
        t.setObjectName("SectionTitle")
        layout.addWidget(t)
        return card, layout

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        title = QLabel("演奏控制")
        title.setObjectName("PageTitle")
        self.state_label = QLabel("就绪")
        self.state_label.setObjectName("PageSub")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(self.state_label)
        header.addStretch(1)
        root.addLayout(header)

        # 选择乐谱
        card, lay = self._card("选择乐谱")
        label = QLabel("乐谱")
        label.setObjectName("FieldLabel")
        lay.addWidget(label)
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_select)
        lay.addWidget(self.combo)
        root.addWidget(card)

        # 演奏速度 + 信息卡
        card, lay = self._card("演奏速度")
        bpm_row = QHBoxLayout()
        bpm_row.setSpacing(16)
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(30, 300)
        self.bpm_spin.setValue(100)
        self.bpm_spin.setMinimumWidth(90)
        self.bpm_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bpm_slider = QSlider(Qt.Orientation.Horizontal)
        self.bpm_slider.setRange(30, 300)
        self.bpm_slider.setValue(100)
        self.bpm_spin.valueChanged.connect(self.bpm_slider.setValue)
        self.bpm_slider.valueChanged.connect(self.bpm_spin.setValue)
        bpm_row.addWidget(self.bpm_spin)
        bpm_row.addWidget(self.bpm_slider, 1)
        unit = QLabel("拍/分钟")
        unit.setObjectName("HintText")
        bpm_row.addWidget(unit)
        lay.addLayout(bpm_row)

        info = QFrame()
        info.setStyleSheet(
            f"background: #1E1E28; border-radius: 8px;"
        )
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(24)
        self.info_name = self._info_item(info_layout, "乐谱名称", "-")
        self.info_count = self._info_item(info_layout, "音符数", "-")
        self.info_duration = self._info_item(info_layout, "预计时长", "-")
        lay.addWidget(info)
        root.addWidget(card)

        # 控制
        card, lay = self._card("演奏控制")
        ctrl_row = QHBoxLayout()
        self.play_btn = QPushButton("开始演奏")
        self.play_btn.setObjectName("BtnPrimary")
        self.play_btn.setMinimumWidth(120)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("BtnStop")
        self.stop_btn.setMinimumWidth(80)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("BtnSecondary")
        self.reset_btn.setMinimumWidth(80)
        self.reset_btn.setEnabled(False)
        self.reset_btn.setToolTip("仅在停止(暂停)后可用:清空演奏进度,下次从头开始")
        self.reset_btn.clicked.connect(self._reset)
        ctrl_row.addWidget(self.play_btn)
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addWidget(self.reset_btn)
        ctrl_row.addStretch(1)
        lay.addLayout(ctrl_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        lay.addWidget(self.progress_bar)
        pos_row = QHBoxLayout()
        self.pos_label = QLabel("0 / 0")
        self.pos_label.setStyleSheet(f"font-family: Consolas; color: {BRAND}; font-weight: 600; font-size: 14px;")
        pos_row.addWidget(self.pos_label)
        pos_row.addStretch(1)
        self.progress_state = QLabel("就绪")
        self.progress_state.setObjectName("HintText")
        pos_row.addWidget(self.progress_state)
        lay.addLayout(pos_row)

        hint = QLabel("演奏时请将焦点切到游戏窗口 · 按 F8 可随时暂停演奏")
        hint.setFixedHeight(40)
        hint.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        hint.setStyleSheet(
            f"color: #EDEDF2; font-size: 13px; padding: 0 14px; "
            f"background: #1E1E28; border-radius: 8px; border: 1px solid #26262F;"
        )
        lay.addWidget(hint)
        root.addWidget(card)
        root.addStretch(1)

    def _info_item(self, layout, label_text, value_text):
        col = QVBoxLayout()
        col.setSpacing(2)
        label = QLabel(label_text)
        label.setStyleSheet(f"font-size: 12px; color: {INK_3};")
        value = QLabel(value_text)
        value.setStyleSheet(f"font-size: 15px; font-weight: 600; color: #EDEDF2; font-family: Consolas;")
        col.addWidget(label)
        col.addWidget(value)
        layout.addLayout(col)
        return value

    def refresh(self):
        self._clear_pause()
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in self._db.list_scores():
            self.combo.addItem(f"{s['name']}  (BPM {s['bpm_default']})", s["id"])
        self.combo.setCurrentIndex(-1)
        self.combo.blockSignals(False)
        if self.combo.count() > 0:
            self.combo.setCurrentIndex(0)
        else:
            self._score_id = None
            self.info_name.setText("-")
            self.info_count.setText("-")
            self.info_duration.setText("-")
            self.play_btn.setEnabled(False)

    def select_score(self, score_id: int):
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == score_id:
                self.combo.setCurrentIndex(i)
                return

    def _on_select(self):
        self._score_id = self.combo.currentData()
        self._clear_pause()
        if self._score_id is None:
            self.play_btn.setEnabled(False)
            return
        score = self._db.get_score(self._score_id)
        if score is None:
            return
        self.bpm_spin.setValue(score["bpm_default"])
        self.info_name.setText(score["name"])
        self.info_count.setText(str(len(score["notes"])))
        self.info_duration.setText(f"{self._estimate_seconds(score['notes'], self.bpm_spin.value())} 秒")
        self.play_btn.setEnabled(not self._player.is_playing)

    def _clear_pause(self):
        """回到未开始态:清空暂停进度与按钮状态。"""
        self._paused_done = 0
        self._paused_total = 0
        self.play_btn.setText("开始演奏")
        self.reset_btn.setEnabled(False)

    def _estimate_seconds(self, notes, bpm):
        beat_ms = 60000.0 / max(1, bpm)
        total_ms = sum(n["dur"] * beat_ms for n in notes)
        total_ms += self._gap_ms * len(notes)
        return round(total_ms / 1000.0, 1)

    def _play(self):
        if self._score_id is None:
            return
        score = self._db.get_score(self._score_id)
        if not score or not score["notes"]:
            AppDialog.show_warning(self, "提示", "该乐谱没有音符数据")
            return
        start_index = self._paused_done if self._paused_done > 0 else 0
        self._pending = (score["notes"], self.bpm_spin.value(), start_index)
        self._had_error = False
        self._countdown_left = 3
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.reset_btn.setEnabled(False)
        resume_hint = f"从第 {start_index} 音符继续" if start_index > 0 else ""
        self.state_label.setText(f"3 秒后演奏: 《{score['name']}》 {resume_hint}".strip())
        self.progress_state.setText(f"{self._countdown_left} 秒后开始演奏,请切换到游戏窗口...")
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._countdown_tick)
        self._countdown_timer.start(1000)

    def _countdown_tick(self):
        self._countdown_left -= 1
        if self._countdown_left > 0:
            self.progress_state.setText(f"{self._countdown_left} 秒后开始演奏,请切换到游戏窗口...")
            return
        self._countdown_timer.stop()
        notes, bpm, start_index = self._pending
        self._player.play(notes, bpm, self._hold_ratio, self._gap_ms, start_index=start_index)
        self.state_label.setText(f"演奏中 BPM {bpm}")
        self.progress_state.setText("演奏中...")

    def _stop(self):
        timer = getattr(self, "_countdown_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_state.setText("已取消")
            return
        self._player.stop()
        self.progress_state.setText("正在暂停...")

    def _on_progress(self, done, total):
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)
        self.pos_label.setText(f"{done} / {total}")

    def _on_paused(self, done, total):
        """停止(暂停):进度保留,可继续或重置。"""
        self._paused_done = done
        self._paused_total = total
        self.play_btn.setEnabled(True)
        self.play_btn.setText("继续演奏" if done > 0 else "开始演奏")
        self.stop_btn.setEnabled(False)
        self.reset_btn.setEnabled(True)
        self.state_label.setText("已暂停")
        self.progress_state.setText(f"已暂停于 {done} / {total} · 「继续演奏」或「重置」")

    def _reset(self):
        """重置:清空暂停进度,回到未开始态(仅在暂停态可点击)。"""
        self._clear_pause()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.pos_label.setText("0 / 0")
        self.state_label.setText("就绪")
        self.progress_state.setText("进度已重置")

    def _on_error(self, msg: str):
        self._had_error = True
        self.state_label.setText("演奏出错")
        self.progress_state.setText(f"出错: {msg}")

    def _on_finished(self, normal):
        self._clear_pause()
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if normal:
            self.state_label.setText("就绪")
            self.progress_state.setText("演奏完成")
        elif not self._had_error:
            self.state_label.setText("就绪")
            self.progress_state.setText("已停止")
