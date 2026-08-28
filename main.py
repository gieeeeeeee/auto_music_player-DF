"""入口:加载配置,组装数据库/识别器/按键映射/演奏器,启动 GUI(暗色琥珀金主题)。"""

import ctypes
import os
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


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_config()
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