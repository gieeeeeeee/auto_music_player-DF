"""乐谱数据库(SQLite)。"""

import json
import os
import sqlite3
from datetime import datetime


class ScoreDB:
    """乐谱库:一份乐谱记录一次,重复演奏无需重新上传。"""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_file TEXT,
                source_type TEXT,
                raw_text TEXT,
                notes_json TEXT NOT NULL,
                bpm_default INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def add_score(self, name, notes, raw_text="", source_file="", source_type="", bpm_default=100):
        cur = self.conn.execute(
            "INSERT INTO scores (name, source_file, source_type, raw_text, notes_json, bpm_default, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                source_file,
                source_type,
                raw_text,
                json.dumps(notes, ensure_ascii=False),
                bpm_default,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_score(self, score_id, name, notes, raw_text="", bpm_default=100):
        self.conn.execute(
            "UPDATE scores SET name=?, raw_text=?, notes_json=?, bpm_default=? WHERE id=?",
            (name, raw_text, json.dumps(notes, ensure_ascii=False), bpm_default, score_id),
        )
        self.conn.commit()

    def list_scores(self):
        rows = self.conn.execute(
            "SELECT id, name, source_file, source_type, bpm_default, created_at "
            "FROM scores ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_score(self, score_id):
        row = self.conn.execute("SELECT * FROM scores WHERE id=?", (score_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["notes"] = json.loads(d.pop("notes_json"))
        return d

    def delete_score(self, score_id):
        self.conn.execute("DELETE FROM scores WHERE id=?", (score_id,))
        self.conn.commit()
