"""入口:加载配置,组装数据库/识别器/按键映射/演奏器,启动 GUI(暗色琥珀金主题)。"""

import ctypes
import os
import shutil
import sys

import yaml
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

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    win = MainWindow(cfg, db, keymap, recognizer, player, settings_store)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()