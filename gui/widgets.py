"""自绘暗色提示框:模态 + 圆角卡片 + 语义色图标,替代系统 QMessageBox。

用法:
    AppDialog.show_info(parent, "标题", "正文")
    AppDialog.show_warning(parent, "标题", "正文")
    AppDialog.show_error(parent, "标题", "正文")
    AppDialog.show_success(parent, "标题", "正文")
    ok = AppDialog.confirm(parent, "标题", "正文")
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)
from gui.theme import (
    BRAND,
    INK,
    INK_2,
    LINE_2,
    STATE_ERROR,
    STATE_INFO,
    STATE_SUCCESS,
    STATE_WARNING,
    SURFACE,
)

# 类型 -> (颜色, 图标字符)
_STYLES = {
    "success": (STATE_SUCCESS, "✓"),
    "info": (BRAND, "i"),
    "warning": (STATE_WARNING, "!"),
    "error": (STATE_ERROR, "✕"),
    "confirm": (STATE_INFO, "?"),
}

_OK_TEXT = "知道了"


class BottomResizableCard(QFrame):
    """底部边缘可拖拽调整高度的卡片。

    拖动底边(6px 命中区)改变自身固定高度,页面总内容高度随之变化,
    外层 QScrollArea 的总滚动条自动同步。
    """

    EDGE = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min_h = 120
        self._max_h = None
        self._press_y = None
        self._start_h = None
        self.setMouseTracking(True)

    def setup(self, height: int, min_height: int, max_height=None):
        self._min_h = min_height
        self._max_h = max_height
        self.setFixedHeight(height)

    def _on_edge(self, pos) -> bool:
        return self.height() - pos.y() <= self.EDGE

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_edge(e.position().toPoint()):
            self._press_y = e.globalPosition().toPoint().y()
            self._start_h = self.height()
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_y is not None:
            delta = e.globalPosition().toPoint().y() - self._press_y
            new_h = max(self._min_h, self._start_h + delta)
            if self._max_h is not None:
                new_h = min(new_h, self._max_h)
            self.setFixedHeight(new_h)
            e.accept()
            return
        if self._on_edge(e.position().toPoint()):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._press_y is not None:
            self._press_y = None
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)


class AppDialog(QDialog):
    def __init__(self, parent, dtype: str, title: str, message: str, buttons):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._clicked = None
        color, glyph = _STYLES.get(dtype, _STYLES["info"])
        self._build(color, glyph, title, message, buttons)

    def _build(self, color, glyph, title, message, buttons):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {LINE_2}; border-radius: 16px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)
        root.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(14)
        icon = QLabel(glyph)
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {color}26; color: {color}; border: 1px solid {color}55;"
            f"border-radius: 22px; font-size: 19px; font-weight: 700;"
        )
        head.addWidget(icon)
        t = QLabel(title)
        t.setStyleSheet(f"color: {INK}; font-size: 16px; font-weight: 600;")
        t.setWordWrap(True)
        head.addWidget(t, 1, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(head)

        msg = QLabel(message)
        msg.setStyleSheet(f"color: {INK_2}; font-size: 13px;")
        msg.setWordWrap(True)
        lay.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)
        for text, role in buttons:
            btn = QPushButton(text)
            btn.setObjectName("BtnPrimary" if role == "primary" else "BtnSecondary")
            btn.setMinimumWidth(96)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=text: self._on_click(t))
            btn_row.addWidget(btn)
        lay.addLayout(btn_row)

    def _on_click(self, text: str):
        self._clicked = text
        self.accept()

    # ---------- 静态调用接口 ----------

    @staticmethod
    def _popup(parent, dtype, title, message, buttons) -> str:
        dlg = AppDialog(parent, dtype, title, message, buttons)
        dlg.exec()
        return dlg._clicked or ""

    @staticmethod
    def show_info(parent, title, message):
        AppDialog._popup(parent, "info", title, message, [(_OK_TEXT, "primary")])

    @staticmethod
    def show_warning(parent, title, message):
        AppDialog._popup(parent, "warning", title, message, [(_OK_TEXT, "primary")])

    @staticmethod
    def show_error(parent, title, message):
        AppDialog._popup(parent, "error", title, message, [(_OK_TEXT, "primary")])

    @staticmethod
    def show_success(parent, title, message):
        AppDialog._popup(parent, "success", title, message, [(_OK_TEXT, "primary")])

    @staticmethod
    def confirm(parent, title, message) -> bool:
        clicked = AppDialog._popup(
            parent, "confirm", title, message, [("取消", "secondary"), ("确定", "primary")]
        )
        return clicked == "确定"