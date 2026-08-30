"""演奏小窗(副窗口):置顶、半透明、点击不抢焦点、非控件区域鼠标穿透。

设计目标:游戏窗口始终保持前台与焦点,用户通过悬浮小窗控制演奏,
从机制上消除"切窗导致的焦点检测误停"与游戏失焦问题。

关键手段:
- WS_EX_NOACTIVATE:点击小窗按钮只投递鼠标事件、不激活窗口,游戏焦点不被夺走
  (与屏幕键盘同款技术)
- WM_NCHITTEST 原生过滤:控件矩形之外返回 HTTRANSPARENT,鼠标点击穿透到游戏
- WindowStaysOnTopHint + Tool:置顶悬浮且不占任务栏
- 透明度 30%~100%(setWindowOpacity)
非 Windows 平台自动降级:小窗仍可用,但无穿透与免激活特性。
"""

import ctypes
import os
import sys

from PyQt6.QtCore import QAbstractNativeEventFilter, QPoint, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from gui.theme import INK, INK_2, LINE_2, SURFACE

WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

_user32 = ctypes.WinDLL("user32") if sys.platform == "win32" else None
if _user32 is not None:
    _GetWindowLongPtr = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _SetWindowLongPtr = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt", ctypes.c_long * 2),
    ]


def _short16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class _MiniHitTestFilter(QAbstractNativeEventFilter):
    """应用级原生事件过滤器:仅处理小窗自身 hwnd 的 WM_NCHITTEST。

    - 不覆写 QWidget.nativeEvent——后者会在原生窗口创建期重入 Python 虚方法,
      触发 PyQt6 原生崩溃;应用级过滤器在创建期不介入,规避该问题
    - 判定使用预缓存的物理坐标矩形,回调内零 Qt 调用(纯 int 比较),无重入风险
    """

    def __init__(self, mini: "MiniPlayerWindow"):
        super().__init__()
        self._mini = mini

    def nativeEventFilter(self, eventType, message):
        mini = self._mini
        if (
            mini is not None
            and mini._native_hwnd
            and eventType == b"windows_generic_MSG"
        ):
            try:
                msg = _MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST and (msg.hwnd or 0) == mini._native_hwnd:
                    mode = os.environ.get("AMP_FILTER_MODE")
                    if mode == "B":
                        return False, 0
                    x = _short16(msg.lParam & 0xFFFF)
                    y = _short16((msg.lParam >> 16) & 0xFFFF)
                    hit = None
                    for rx, ry, rw, rh in mini._phys_rects:
                        if rx <= x < rx + rw and ry <= y < ry + rh:
                            hit = (rx, ry, rw, rh)
                            break
                    if os.environ.get("AMP_DEBUG_HITTEST"):
                        print(f"HITTEST: xy=({x},{y}) -> hit={hit}", flush=True)
                    if hit is not None:
                        return False, 0
                    if mode == "C":
                        return False, 0
                    return True, HTTRANSPARENT
            except Exception as e:
                if os.environ.get("AMP_DEBUG_HITTEST"):
                    print(f"HITTEST-ERR: {e}", flush=True)
        return False, 0


class MiniPlayerWindow(QWidget):
    """简化演奏控制小窗;控制逻辑全部复用 PlayerTab,自身零业务逻辑。"""

    WIDTH, HEIGHT = 420, 160
    OPACITY_MIN, OPACITY_MAX, OPACITY_DEFAULT = 30, 100, 85

    def __init__(self, player_tab, on_restore):
        super().__init__(None)
        self._tab = player_tab
        self._on_restore = on_restore
        self._drag_pos = None
        self._style_applied = False
        self._native_hwnd = 0
        self._phys_rects = []   # 可点击区域的物理坐标缓存(原生回调内纯 int 比较)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._place_initial()
        self._build()
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(200)
        self._sync_timer.timeout.connect(self._sync_state)
        if sys.platform == "win32" and not os.environ.get("AMP_DISABLE_HITFILTER"):
            self._hit_filter = _MiniHitTestFilter(self)
            QApplication.instance().installNativeEventFilter(self._hit_filter)

    # ---------- 构建 ----------

    def _place_initial(self):
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.top() + 60)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {SURFACE}; border: 1px solid {LINE_2}; border-radius: 12px; }}"
        )
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 8, 14, 12)
        lay.setSpacing(6)

        self.drag_strip = QLabel("⠿ 演奏小窗 — 拖动移动 · 点击不夺游戏焦点")
        self.drag_strip.setStyleSheet(
            f"color: {INK_2}; font-size: 11px; background: transparent; border: none;"
        )
        self.drag_strip.setFixedHeight(16)
        lay.addWidget(self.drag_strip)

        info_row = QHBoxLayout()
        self.score_label = QLabel("-")
        self.score_label.setStyleSheet(f"color: {INK}; font-size: 12px; font-weight: 600; border: none;")
        self.state_label = QLabel("就绪")
        self.state_label.setStyleSheet(f"color: {INK_2}; font-size: 11px; border: none;")
        info_row.addWidget(self.score_label, 1)
        info_row.addWidget(self.state_label)
        lay.addLayout(info_row)

        bar_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(10)
        self.progress.setTextVisible(False)
        bar_row.addWidget(self.progress, 1)
        self.pos_label = QLabel("0 / 0")
        self.pos_label.setStyleSheet(f"color: {INK_2}; font-size: 11px; border: none;")
        bar_row.addWidget(self.pos_label)
        lay.addLayout(bar_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.play_btn = QPushButton("开始演奏")
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("BtnStop")
        self.reset_btn = QPushButton("重置")
        self.restore_btn = QPushButton("还原主窗")
        for b in (self.play_btn, self.stop_btn, self.reset_btn, self.restore_btn):
            b.setFixedHeight(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self._tab.mini_play)
        self.stop_btn.clicked.connect(self._tab.mini_stop)
        self.reset_btn.clicked.connect(self._tab.mini_reset)
        self.restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self.play_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.restore_btn)
        lay.addLayout(btn_row)

        opacity_row = QHBoxLayout()
        op_label = QLabel("透明度")
        op_label.setStyleSheet(f"color: {INK_2}; font-size: 11px; border: none;")
        self.opacity_label = QLabel(f"{self.OPACITY_DEFAULT}%")
        self.opacity_label.setStyleSheet(f"color: {INK_2}; font-size: 11px; border: none;")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(self.OPACITY_MIN, self.OPACITY_MAX)
        self.opacity_slider.setValue(self.OPACITY_DEFAULT)
        opacity_row.addWidget(op_label)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_label)
        lay.addLayout(opacity_row)

        self.setWindowOpacity(self.OPACITY_DEFAULT / 100.0)
        self.opacity_slider.valueChanged.connect(self._on_opacity)

    def _on_opacity(self, v: int):
        self.opacity_label.setText(f"{v}%")
        self.setWindowOpacity(v / 100.0)

    # ---------- 状态镜像 ----------

    def _refresh_phys_rects(self):
        """缓存可点击区域的物理坐标(逻辑坐标 × devicePixelRatio)。

        物理矩形随文本变化导致的布局偏移而刷新:由 200ms 状态镜像与
        移动/缩放事件共同触发;原生回调路径只读取缓存,不做任何 Qt 调用。
        """
        dpr = self.devicePixelRatioF() or 1.0
        rects = []
        for w in self._clickable_widgets():
            g = w.mapToGlobal(QPoint(0, 0))
            rects.append((round(g.x() * dpr), round(g.y() * dpr),
                          round(w.width() * dpr), round(w.height() * dpr)))
        self._phys_rects = rects

    def _clickable_widgets(self) -> list:
        ws = [w for w in self.findChildren((QPushButton, QSlider)) if w.isVisible()]
        ws.append(self.drag_strip)
        return ws

    def _sync_state(self):
        self._refresh_phys_rects()
        snap = self._tab.snapshot_for_mini()
        self.score_label.setText(snap["score"])
        self.state_label.setText(snap["state"])
        self.pos_label.setText(snap["pos"])
        self.progress.setRange(0, max(1, snap["max"]))
        self.progress.setValue(snap["value"])
        self.play_btn.setText(snap["play_text"])
        self.play_btn.setEnabled(snap["play_enabled"])
        self.stop_btn.setEnabled(snap["stop_enabled"])
        self.reset_btn.setEnabled(snap["reset_enabled"])

    # ---------- 置顶 / 免激活 / 穿透 ----------

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self._style_applied:
            try:
                self._native_hwnd = int(self.winId())
                ex = _GetWindowLongPtr(self._native_hwnd, GWL_EXSTYLE)
                _SetWindowLongPtr(self._native_hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
                self._style_applied = True
            except Exception:
                pass
        self._sync_state()
        self._sync_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_timer.stop()

    def moveEvent(self, event):
        self._refresh_phys_rects()
        super().moveEvent(event)

    def resizeEvent(self, event):
        self._refresh_phys_rects()
        super().resizeEvent(event)

    # ---------- 鼠标穿透 ----------

    def hit_test_transparent(self, global_x: int, global_y: int) -> bool:
        """物理屏幕坐标落在可点击矩形之外 → 穿透(点击落到下层游戏窗口)。

        物理坐标直接与预缓存矩形比较,与原生回调路径完全一致。
        """
        for rx, ry, rw, rh in self._phys_rects:
            if rx <= global_x < rx + rw and ry <= global_y < ry + rh:
                return False
        return True

    # ---------- 拖动(经拖动条,该区域不穿透) ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
