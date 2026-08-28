"""主窗口:自绘标题栏(标准 Windows 风格按钮) + 侧边栏导航 + 页面堆栈 + 状态栏。"""

import ctypes

from pynput import keyboard as pk
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.library_tab import LibraryTab
from gui.player_tab import PlayerTab
from gui.settings_tab import SettingsTab
from gui.theme import BRAND, INK, INK_2, INK_3, STATE_ERROR, STATE_SUCCESS, STATE_WARNING, SURFACE_3
from gui.upload_tab import UploadTab

NAV_ITEMS = [
    ("上传识别", "↑"),
    ("乐谱库", "♪"),
    ("演奏控制", "▶"),
    ("模型设置", "⚙"),
]

TITLE_BAR_HEIGHT = 32
WIN_BTN_WIDTH = 46
SIDEBAR_WIDTH = 240
STATUS_BAR_HEIGHT = 28


class TitleBarBtn(QAbstractButton):
    """标准 Windows 风格标题栏按钮(QPainter 自绘横线/方框/X)。"""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind  # "min" / "max" / "close"
        self._hover = False
        self._is_maximized = False
        self.setFixedSize(WIN_BTN_WIDTH, TITLE_BAR_HEIGHT)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(
            {"min": "最小化", "max": "最大化", "close": "关闭"}[kind]
        )

    def set_maximized(self, maximized: bool):
        if self._is_maximized != maximized:
            self._is_maximized = maximized
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._hover:
            if self._kind == "close":
                p.fillRect(0, 0, w, h, QColor(STATE_ERROR))
                fg = QColor("#FFFFFF")
            else:
                p.fillRect(0, 0, w, h, QColor(SURFACE_3))
                fg = QColor(INK)
        else:
            fg = QColor(INK_2)

        pen = QPen(fg, 1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = w // 2, h // 2
        if self._kind == "min":
            p.drawLine(cx - 5, cy, cx + 5, cy)
        elif self._kind == "max":
            if self._is_maximized:
                p.drawRect(cx - 4, cy - 1, 8, 8)
                p.drawLine(cx - 2, cy - 1, cx - 2, cy - 3)
                p.drawLine(cx - 2, cy - 3, cx + 5, cy - 3)
                p.drawLine(cx + 5, cy - 3, cx + 5, cy + 3)
                p.drawLine(cx + 5, cy + 3, cx + 4, cy + 3)
            else:
                p.drawRect(cx - 5, cy - 5, 10, 10)
        elif self._kind == "close":
            p.setPen(QPen(fg, 1.2))
            p.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
            p.drawLine(cx + 5, cy - 5, cx - 5, cy + 5)


class TitleBar(QWidget):
    minimize_requested = pyqtSignal()
    maximize_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        self.title_label = QLabel("自动演奏器")
        self.title_label.setObjectName("TitleBarTitle")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.btn_min = TitleBarBtn("min")
        self.btn_max = TitleBarBtn("max")
        self.btn_close = TitleBarBtn("close")
        self.btn_min.clicked.connect(self.minimize_requested.emit)
        self.btn_max.clicked.connect(self.maximize_requested.emit)
        self.btn_close.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)


class MainWindow(QMainWindow):
    def __init__(self, cfg, db, keymap, recognizer, player, settings_store):
        super().__init__()
        self._cfg = cfg
        self._settings_store = settings_store
        self._drag_pos = None
        self._is_maximized = False
        self._normal_geometry = None

        self.setWindowTitle("自动演奏器")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.resize(1080, 720)
        self.setMinimumSize(900, 600)

        self.upload_tab = UploadTab(db, recognizer, keymap)
        self.library_tab = LibraryTab(db)
        self.player_tab = PlayerTab(db, player, cfg.get("player", {}))
        self.settings_tab = SettingsTab(settings_store)

        self._build_ui()

        self.upload_tab.saved.connect(self.library_tab.refresh)
        self.upload_tab.saved.connect(self.player_tab.refresh)
        self.library_tab.go_play.connect(self._go_play)
        self.settings_tab.providers_saved.connect(self._on_providers_saved)

        hotkey = str(cfg.get("player", {}).get("stop_hotkey", "F8")).lower()
        self._hotkey_listener = pk.GlobalHotKeys({f"<{hotkey}>": player.stop})
        self._hotkey_listener.start()

        self.player_tab.refresh()
        self.settings_tab.refresh_provider_status()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar()
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximize)
        self.title_bar.close_requested.connect(self.close)
        root_layout.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(20, 18, 20, 14)
        logo_text = QLabel("自动演奏器")
        logo_text.setObjectName("SidebarLogoText")
        logo_text.setStyleSheet(f"color: {BRAND};")
        logo_row.addWidget(logo_text)
        sidebar_layout.addLayout(logo_row)

        self.nav = QListWidget()
        self.nav.setObjectName("SidebarNav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for text, icon in NAV_ITEMS:
            item = QListWidgetItem(f"{icon}  {text}")
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._switch_page)
        sidebar_layout.addWidget(self.nav, 1)

        footer = QLabel("v1.0")
        footer.setObjectName("SidebarFooter")
        sidebar_layout.addWidget(footer)

        body.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.upload_tab)
        self.stack.addWidget(self.library_tab)
        self.stack.addWidget(self.player_tab)
        self.stack.addWidget(self.settings_tab)
        body.addWidget(self.stack, 1)

        root_layout.addLayout(body, 1)

        status_bar = QWidget()
        status_bar.setObjectName("StatusBar")
        status_bar.setFixedHeight(STATUS_BAR_HEIGHT)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(16, 0, 16, 0)
        status_layout.setSpacing(12)
        dot = QLabel()
        dot.setObjectName("StatusDot")
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusText")
        hotkey_label = QLabel("按 F8 可随时停止演奏")
        hotkey_label.setObjectName("StatusText")
        hotkey_label.setToolTip(
            "全局热键 F8:无论焦点在哪个窗口,按下 F8 会立即停止当前演奏"
        )
        status_layout.addWidget(dot)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)
        try:
            admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            admin = False
        perm_label = QLabel(
            "管理员权限" if admin else "普通权限 · 游戏收不到按键时请以管理员运行"
        )
        perm_label.setObjectName("StatusText")
        perm_label.setStyleSheet(
            f"color: {STATE_SUCCESS};" if admin else f"color: {STATE_WARNING};"
        )
        status_layout.addWidget(perm_label)
        status_layout.addWidget(hotkey_label)
        status_layout.addWidget(QLabel("v1.0", objectName="StatusText"))
        root_layout.addWidget(status_bar)

        self.setCentralWidget(root)
        self.nav.setCurrentRow(0)

    def _switch_page(self, row: int):
        self.stack.setCurrentIndex(row)

    def _go_play(self, score_id: int):
        self.stack.setCurrentIndex(2)
        self.player_tab.select_score(score_id)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def _on_providers_saved(self):
        from core.recognizer import get_recognizer_from_provider

        provider = self._settings_store.get_active()
        self.upload_tab.set_recognizer(get_recognizer_from_provider(provider))
        self.set_status(
            f"识别模型: {provider['name']} · {provider['model']}" if provider else "识别模型: 内置样例(stub)"
        )

    # ---------- 无边框窗口拖动/最大化 ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= TITLE_BAR_HEIGHT:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.position().y() <= TITLE_BAR_HEIGHT:
            self._toggle_maximize()

    def _toggle_maximize(self):
        if self._is_maximized:
            self.showNormal()
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self.title_bar.btn_max.set_maximized(False)
        else:
            self._normal_geometry = self.geometry()
            self.showMaximized()
            self.title_bar.btn_max.set_maximized(True)
        self._is_maximized = not self._is_maximized