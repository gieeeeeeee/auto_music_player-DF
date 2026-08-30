"""AI 编谱建议对话框(实验性):描述输入 → 模型生成 → 确认后填入上传页识别框。

结果只经用户点击「填入识别结果」才进入既有校对/保存流程,取消即丢弃。
"""

import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from core.advisor import generate_advice
from gui.theme import INK, INK_2, LINE_2, SURFACE
from gui.widgets import AppDialog


class AdvisorDialog(QDialog):
    advice_ready = pyqtSignal(object)
    advice_failed = pyqtSignal(str)

    def __init__(self, parent, advisor_cfg, provider, on_accept):
        super().__init__(parent)
        self._cfg = advisor_cfg or {}
        self._provider = provider
        self._on_accept = on_accept   # 回调(简谱文本),由上传页填入识别结果
        self._result = None
        self.setWindowTitle("AI 编谱建议(实验性)")
        self.setModal(True)
        self.setFixedWidth(560)
        self._build()
        self.advice_ready.connect(self._on_ready)
        self.advice_failed.connect(self._on_failed)

    def _card(self):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {LINE_2}; border-radius: 12px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        return frame, lay

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        card, lay = self._card()
        title = QLabel("AI 编谱建议")
        title.setStyleSheet(f"color: {INK}; font-size: 15px; font-weight: 600;")
        lay.addWidget(title)
        model_name = (self._cfg.get("model") or "").strip() or (self._provider or {}).get("model", "")
        desc = QLabel(
            "输入旋律描述(如:欢快的五声音阶小段)或简谱片段,模型将给出符合 21 键的编谱建议。\n"
            f"使用模型:{model_name or '(未配置)'} · 结果需经你确认后填入识别结果,不会自动保存。"
        )
        desc.setStyleSheet(f"color: {INK_2}; font-size: 12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("例:把 1 2 3 5 扩展成一段带附点节奏的欢快旋律,结尾落在 1")
        self.desc_edit.setFixedHeight(88)
        lay.addWidget(self.desc_edit)
        self.gen_btn = QPushButton("生成建议")
        self.gen_btn.setObjectName("BtnPrimary")
        self.gen_btn.clicked.connect(self._generate)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.gen_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        root.addWidget(card)

        card2, lay2 = self._card()
        tip = QLabel("编谱建议(可修改)")
        tip.setStyleSheet(f"color: {INK}; font-size: 13px; font-weight: 600;")
        lay2.addWidget(tip)
        self.result_edit = QPlainTextEdit()
        self.result_edit.setPlaceholderText("生成的简谱将显示在这里,可直接修改")
        self.result_edit.setFixedHeight(96)
        lay2.addWidget(self.result_edit)
        self.tips_label = QLabel("")
        self.tips_label.setStyleSheet(f"color: {INK_2}; font-size: 12px;")
        self.tips_label.setWordWrap(True)
        lay2.addWidget(self.tips_label)
        self.warn_label = QLabel("")
        self.warn_label.setStyleSheet("color: #E0A34A; font-size: 12px;")
        self.warn_label.setWordWrap(True)
        self.warn_label.hide()
        lay2.addWidget(self.warn_label)
        root.addWidget(card2, 1)

        btn_row2 = QHBoxLayout()
        self.accept_btn = QPushButton("填入识别结果")
        self.accept_btn.setObjectName("BtnPrimary")
        self.accept_btn.setEnabled(False)
        self.accept_btn.clicked.connect(self._accept)
        close_btn = QPushButton("取消")
        close_btn.setObjectName("BtnSecondary")
        close_btn.clicked.connect(self.reject)
        btn_row2.addWidget(self.accept_btn)
        btn_row2.addStretch(1)
        btn_row2.addWidget(close_btn)
        root.addLayout(btn_row2)

    def _generate(self):
        desc = self.desc_edit.toPlainText().strip()
        if not desc:
            AppDialog.show_warning(self, "提示", "请输入旋律描述或简谱片段")
            return
        provider = self._provider or {}
        api_base = provider.get("base_url", "")
        api_key = provider.get("api_key", "")
        model = (self._cfg.get("model") or "").strip() or provider.get("model", "")
        if not api_base or not api_key or not model:
            AppDialog.show_warning(
                self, "提示", "请先在「模型设置」页配置并激活供应商(编谱建议使用其接口)"
            )
            return
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("生成中...")
        self.accept_btn.setEnabled(False)
        t = threading.Thread(
            target=self._worker,
            args=(desc, api_base, api_key, model),
            daemon=True,
        )
        t.start()

    def _worker(self, desc, api_base, api_key, model):
        try:
            result = generate_advice(desc, api_base, api_key, model)
            self.advice_ready.emit(result)
        except Exception as e:
            self.advice_failed.emit(str(e))

    def _on_ready(self, result):
        self._result = result
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("重新生成")
        self.result_edit.setPlainText(result.jianpu_text)
        self.tips_label.setText("\n".join(f"· {t}" for t in result.tips) if result.tips else "")
        if result.warnings:
            self.warn_label.setText("注意:\n" + "\n".join(result.warnings))
            self.warn_label.show()
        else:
            self.warn_label.hide()
        self.accept_btn.setEnabled(result.ok)

    def _on_failed(self, msg):
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("生成建议")
        AppDialog.show_error(self, "生成失败", msg)

    def _accept(self):
        text = self.result_edit.toPlainText().strip()
        if not text:
            AppDialog.show_warning(self, "提示", "建议内容为空")
            return
        self._on_accept(text)
        self.accept()
