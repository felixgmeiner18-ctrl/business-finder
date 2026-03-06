import sqlite3
from datetime import datetime

DB_PATH = "businesses.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT NOT NULL,
                phone     TEXT NOT NULL,
                address   TEXT,
                category  TEXT,
                region    TEXT,
                status    TEXT DEFAULT 'New',
                notes     TEXT DEFAULT '',
                found_at  TEXT
            )
        """)
        conn.commit()


def upsert_business(name, phone, address, category, region):
    """Insert if not already present (match on name+phone)."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM businesses WHERE name=? AND phone=?", (name, phone)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            """INSERT INTO businesses (name, phone, address, category, region, status, notes, found_at)
               VALUES (?, ?, ?, ?, ?, 'New', '', ?)""",
            (name, phone, address, category, region, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return True


def get_businesses(status=None, region=None, category=None):
    query = "SELECT * FROM businesses WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if region:
        query += " AND region LIKE ?"
        params.append(f"%{region}%")
    if category:
        query += " AND category LIKE ?"
        params.append(f"%{category}%")
    query += " ORDER BY found_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_business(business_id, status=None, notes=None):
    fields, params = [], []
    if status is not None:
        fields.append("status=?")
        params.append(status)
    if notes is not None:
        fields.append("notes=?")
        params.append(notes)
    if not fields:
        return
    params.append(business_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE businesses SET {', '.join(fields)} WHERE id=?", params
        )
        conn.commit()


def delete_business(business_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM businesses WHERE id=?", (business_id,))
        conn.commit()
