"""GUI 冒烟测试:启动主窗口 1.5 秒后自动退出,验证无崩溃。
运行: python tests/smoke_gui.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

import main as m


def run():
    cfg = m.load_config()
    db = m.ScoreDB(os.path.join("data", "smoke.db"))
    keymap = m.KeyMap(cfg["keymap"])
    settings_store = m.SettingsStore(os.path.join("data", "smoke_settings.json"))
    recognizer = m.get_recognizer_from_provider(settings_store.get_active())
    player = m.Player(keymap)
    app = QApplication(sys.argv)
    app.setStyleSheet(m.APP_QSS)
    win = m.MainWindow(cfg, db, keymap, recognizer, player, settings_store)
    win.show()
    QTimer.singleShot(1500, app.quit)
    rc = app.exec()
    db.conn.close()
    for f in ("data/smoke.db", "data/smoke_settings.json"):
        if os.path.exists(f):
            os.remove(f)
    print("GUI smoke OK" if rc == 0 else f"GUI smoke rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(run())