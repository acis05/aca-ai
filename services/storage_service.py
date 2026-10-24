import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "storage" / "mapping.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS mapping_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            module TEXT NOT NULL,
            source_signature TEXT,
            mapping_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)


def save_profile(name, source_signature, mapping, schema):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO mapping_profiles(name,platform,module,source_signature,mapping_json) VALUES(?,?,?,?,?)",
            (name, schema["platform"], schema["module"], source_signature, json.dumps(mapping, ensure_ascii=False)),
        )
        return cur.lastrowid


def list_profiles():
    with connect() as conn:
        rows = conn.execute("SELECT id,name,platform,module,source_signature,created_at FROM mapping_profiles ORDER BY id DESC LIMIT 50").fetchall()
        return [dict(r) for r in rows]


def get_profile(profile_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM mapping_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["mapping"] = json.loads(d.pop("mapping_json"))
        return d
