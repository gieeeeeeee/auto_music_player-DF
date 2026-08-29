"""入口:加载配置,组装数据库/识别器/按键映射/演奏器,启动 GUI(暗色琥珀金主题)。"""

import ctypes
import os
import shutil
import sys

import yaml
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from core.database import ScoreDB
from core.keymap import KeyMap
from core.player import Player
from core.recognizer import StubRecognizer, get_recognizer_from_provider
from core.settings_store import SettingsStore
from gui.main_window import MainWindow
from gui.theme import APP_QSS


def load_config(path="config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def app_icon():
    """应用图标:任务栏与窗口图标。"""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), "app.ico"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "app.ico"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico"))
    for c in candidates:
        if c and os.path.exists(c):
            return QIcon(c)
    return None


def ensure_config() -> str:
    """切到数据目录并保证 config.yaml 可用。

    exe 运行:数据落在 exe 旁边;exe 旁没有 config.yaml 时,
    自动释放打包时内嵌的默认配置,保证单文件可运行。
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        target = os.path.join(exe_dir, "config.yaml")
        if not os.path.exists(target):
            bundled = os.path.join(getattr(sys, "_MEIPASS", exe_dir), "config.yaml")
            shutil.copyfile(bundled, target)
        os.chdir(exe_dir)
        return target
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    return "config.yaml"


def resource_path(name: str) -> str:
    """打包后资源在 _MEIPASS 临时目录;开发时在项目根目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def main():
    cfg = load_config(ensure_config())
    app_cfg = cfg.get("app", {})
    data_dir = app_cfg.get("data_dir", "data")
    db = ScoreDB(os.path.join(data_dir, app_cfg.get("db_file", "scores.db")))
    keymap = KeyMap(cfg["keymap"])
    settings_store = SettingsStore(os.path.join(data_dir, "settings.json"))
    provider = settings_store.get_active()
    recognizer = get_recognizer_from_provider(provider) if provider else StubRecognizer()
    player = Player(keymap)

    # Windows 任务栏分组图标:显式 AppUserModelID 让任务栏显示自定义图标而非 Python 默认图标
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AutoMusicPlayer.App")
    except Exception:
        pass

    app = QApplication(sys.argv)
    icon = app_icon()
    if icon:
        app.setWindowIcon(icon)
    app.setStyleSheet(APP_QSS)
    icon_path = resource_path("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    win = MainWindow(cfg, db, keymap, recognizer, player, settings_store)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()