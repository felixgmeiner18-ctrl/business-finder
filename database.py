import os
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "businesses.db")

# Category → priority score (1-5). Higher = more likely to buy a website.
PRIORITY_MAP = {
    # 5 = Hot leads (hospitality, health — customers actively search online)
    "restaurant": 5, "doctors": 5, "dentist": 5, "cafe": 5, "bar": 5,
    "hotel": 5, "guest_house": 5, "clinic": 5, "fast_food": 5, "pub": 5,
    "biergarten": 5, "ice_cream": 5,
    # 4 = High (personal services — regulars + walk-ins)
    "hairdresser": 4, "beauty": 4, "bakery": 4, "florist": 4, "butcher": 4,
    "optician": 4, "massage": 4, "tattoo": 4, "cosmetics": 4, "gym": 4,
    "fitness_centre": 4, "yoga": 4, "pharmacy": 4,
    # 3 = Medium (tradesmen — get jobs via referrals but website helps)
    "car_repair": 3, "electrician": 3, "plumber": 3, "carpenter": 3,
    "painter": 3, "roofer": 3, "hvac": 3, "locksmith": 3, "tailor": 3,
    "shoemaker": 3, "glazier": 3, "gardener": 3, "cleaner": 3,
    # 2 = Low (retail — often chains or low margin)
    "convenience": 2, "clothes": 2, "supermarket": 2, "kiosk": 2,
    "newsagent": 2, "tobacco": 2, "beverages": 2,
}


def compute_priority(category: str) -> int:
    """Return 1-5 priority score for a category. Default 1 for unknown."""
    if not category:
        return 1
    return PRIORITY_MAP.get(category.lower(), 1)


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
                email     TEXT DEFAULT '',
                address   TEXT,
                category  TEXT,
                region    TEXT,
                status    TEXT DEFAULT 'New',
                notes     TEXT DEFAULT '',
                found_at  TEXT,
                follow_up TEXT,
                website_url TEXT
            )
        """)
        # Migrate existing tables: add new columns if missing
        cursor = conn.execute("PRAGMA table_info(businesses)")
        columns = {row[1] for row in cursor.fetchall()}
        if "follow_up" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN follow_up TEXT")
        if "website_url" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN website_url TEXT")
        if "email" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN email TEXT DEFAULT ''")
        if "site_generated" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN site_generated INTEGER DEFAULT 0")
        if "site_variation" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN site_variation INTEGER")
        if "site_sections" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN site_sections TEXT")

        # Indices for fast filtering + sorting
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status   ON businesses(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_region   ON businesses(region)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON businesses(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_found_at ON businesses(found_at DESC)")

        # Settings table for configurable signature etc.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Contact submissions table for agency website
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_submissions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                email      TEXT NOT NULL,
                phone      TEXT DEFAULT '',
                message    TEXT NOT NULL,
                created_at TEXT
            )
        """)
        conn.commit()


def upsert_business(name, phone, address, category, region, email=""):
    """Insert if not already present (match on name+phone)."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM businesses WHERE name=? AND phone=?", (name, phone)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            """INSERT INTO businesses (name, phone, email, address, category, region, status, notes, found_at)
               VALUES (?, ?, ?, ?, ?, ?, 'New', '', ?)""",
            (name, phone, email, address, category, region, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return True


def get_businesses(status=None, region=None, category=None, limit=500, offset=0):
    base = "FROM businesses WHERE 1=1"
    params = []
    if status:
        base += " AND status=?"
        params.append(status)
    if region:
        base += " AND region LIKE ?"
        params.append(f"%{region}%")
    if category:
        base += " AND category LIKE ?"
        params.append(f"%{category}%")

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * {base} ORDER BY found_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["priority"] = compute_priority(d.get("category"))
        results.append(d)
    results.sort(key=lambda b: -b["priority"])
    return {"items": results, "total": total, "limit": limit, "offset": offset}


def update_business(business_id, status=None, notes=None, follow_up=None, website_url=None):
    fields, params = [], []
    if status is not None:
        fields.append("status=?")
        params.append(status)
    if notes is not None:
        fields.append("notes=?")
        params.append(notes)
    if follow_up is not None:
        fields.append("follow_up=?")
        params.append(follow_up if follow_up else None)
    if website_url is not None:
        fields.append("website_url=?")
        params.append(website_url)
    if not fields:
        return
    params.append(business_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE businesses SET {', '.join(fields)} WHERE id=?", params
        )
        conn.commit()


def get_business(business_id):
    """Get a single business by ID."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
    if row:
        d = dict(row)
        d["priority"] = compute_priority(d.get("category"))
        return d
    return None


def delete_business(business_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM businesses WHERE id=?", (business_id,))
        conn.commit()


def update_site_info(business_id, variation, sections_json):
    with get_conn() as conn:
        conn.execute(
            "UPDATE businesses SET site_generated=1, site_variation=?, site_sections=? WHERE id=?",
            (variation, sections_json, business_id),
        )
        conn.commit()


def save_contact_submission(name, email, phone, message):
    from datetime import datetime
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO contact_submissions (name, email, phone, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, email, phone, message, datetime.utcnow().isoformat()),
        )
        conn.commit()


_SETTINGS_DEFAULTS = {
    "sender_name": "",
    "sender_company": "PageBuilder",
    "sender_email": "",
    "sender_phone": "",
}


def get_settings() -> dict:
    """Return all settings as a dict, with defaults for missing keys."""
    result = dict(_SETTINGS_DEFAULTS)
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for r in rows:
        result[r["key"]] = r["value"]
    return result


def save_settings(data: dict):
    """Upsert settings from a dict."""
    with get_conn() as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        conn.commit()


def get_contact_submissions():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM contact_submissions ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]
