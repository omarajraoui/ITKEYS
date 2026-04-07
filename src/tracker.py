import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "applications.db")


def get_db(db_path=None):
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            track TEXT NOT NULL,
            status TEXT DEFAULT 'to_apply',
            apply_date TEXT,
            follow_up_date TEXT,
            apply_link TEXT,
            notes TEXT,
            output_dir TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def add_application(company, role, track, output_dir, apply_link="", notes="", db_path=None):
    conn = get_db(db_path)
    now = datetime.now().strftime("%Y-%m-%d")
    follow_up = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO applications (company, role, track, apply_date, follow_up_date, apply_link, notes, output_dir) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (company, role, track, now, follow_up, apply_link, notes, output_dir),
    )
    conn.commit()
    conn.close()


def update_status(app_id, status, db_path=None):
    conn = get_db(db_path)
    conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
    conn.commit()
    conn.close()


def update_notes(app_id, notes, db_path=None):
    conn = get_db(db_path)
    conn.execute("UPDATE applications SET notes = ? WHERE id = ?", (notes, app_id))
    conn.commit()
    conn.close()


def list_applications(status=None, track=None, db_path=None):
    conn = get_db(db_path)
    query = "SELECT * FROM applications WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if track:
        query += " AND track = ?"
        params.append(track)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
