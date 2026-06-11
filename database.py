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
    # 3 = Medium (trades niche additions, 2026-04-23 letter-pipeline patch)
    "heating_engineer": 3, "metal_construction": 3, "tiler": 3,
    "stonemason": 3, "plasterer": 3, "floorer": 3, "handyman": 3,
    "gasfitter": 3,
    # 2 = Low (retail — often chains or low margin)
    "convenience": 2, "clothes": 2, "supermarket": 2, "kiosk": 2,
    "newsagent": 2, "tobacco": 2, "beverages": 2,
}

# Valid letter statuses — any transition is validated server-side.
LETTER_STATUS_VALUES = {
    "pending_review",  # generated, awaiting Felix's approval
    "approved",        # Felix approved, ready for send script
    "sent",            # submitted to Letterxpress, transaction_id recorded
    "delivered",       # Letterxpress confirmed delivery (optional / future)
    "rejected",        # Felix rejected; reason logged; row kept for audit
    "failed",          # Letterxpress rejected submission (API error)
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
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                phone       TEXT DEFAULT '',
                email       TEXT DEFAULT '',
                address     TEXT,
                postal_code TEXT DEFAULT '',
                category    TEXT,
                region      TEXT,
                status      TEXT DEFAULT 'New',
                notes       TEXT DEFAULT '',
                found_at    TEXT,
                follow_up   TEXT,
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
        if "postal_code" not in columns:
            conn.execute("ALTER TABLE businesses ADD COLUMN postal_code TEXT DEFAULT ''")
        if "priority" not in columns:
            # NULL = never scored; verify-local.py writes a 1-10 quality score
            conn.execute("ALTER TABLE businesses ADD COLUMN priority INTEGER")
        # Indices for fast filtering + sorting
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status   ON businesses(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_region   ON businesses(region)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON businesses(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_found_at ON businesses(found_at DESC)")

        # ─── letters table (2026-04-23 letter-pipeline patch) ───
        conn.execute("""
            CREATE TABLE IF NOT EXISTS letters (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id       INTEGER NOT NULL,
                tracking_code     TEXT NOT NULL UNIQUE,
                template_version  TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending_review',
                pdf_bytes         BLOB,
                generated_at      TEXT NOT NULL,
                approved_at       TEXT,
                sent_at           TEXT,
                delivered_at      TEXT,
                transaction_id    TEXT,
                rejection_reason  TEXT,
                FOREIGN KEY (business_id) REFERENCES businesses(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_letters_status        ON letters(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_letters_business_id   ON letters(business_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_letters_generated_at  ON letters(generated_at DESC)")

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
        # Lander visit log (2026-06-11 visit-tracking patch): one row per page
        # load of /VBxx — the exact per-letter scan signal. Cloudflare analytics
        # is sampled and bot-polluted; this table is ground truth.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lander_visits (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_code TEXT NOT NULL,
                visited_at    TEXT NOT NULL,
                user_agent    TEXT DEFAULT '',
                referer       TEXT DEFAULT '',
                ip_hash       TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visits_code ON lander_visits(tracking_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_visits_at   ON lander_visits(visited_at DESC)")
        conn.commit()


def upsert_business(name, phone, address, category, region, email="", postal_code=""):
    """Insert if not already present. Match on (name, phone) when phone is set,
    else on (name, postal_code, address) to avoid duplicates from trades that lack a phone."""
    with get_conn() as conn:
        if phone:
            existing = conn.execute(
                "SELECT id FROM businesses WHERE name=? AND phone=?", (name, phone)
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM businesses WHERE name=? AND postal_code=? AND address=?",
                (name, postal_code, address),
            ).fetchone()
        if existing:
            return False
        conn.execute(
            """INSERT INTO businesses (name, phone, email, address, postal_code, category, region, status, notes, found_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'New', '', ?)""",
            (name, phone, email, address, postal_code, category, region, datetime.utcnow().isoformat()),
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
        # stored quality score (verify-local.py) wins over the category heuristic
        if d.get("priority") is None:
            d["priority"] = compute_priority(d.get("category"))
        results.append(d)
    results.sort(key=lambda b: -b["priority"])
    return {"items": results, "total": total, "limit": limit, "offset": offset}


def update_business(business_id, status=None, notes=None, follow_up=None,
                    website_url=None, priority=None, postal_code=None):
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
    if priority is not None:
        fields.append("priority=?")
        params.append(int(priority))
    if postal_code is not None:
        fields.append("postal_code=?")
        params.append(postal_code)
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
        if d.get("priority") is None:
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


# ─────────────────────────────────────────────────────────────────
# Letters pipeline (2026-04-23 letter-pipeline patch)
# ─────────────────────────────────────────────────────────────────

# Metadata-only column list (excludes pdf_bytes BLOB for fast list queries)
_LETTER_META_COLS = (
    "id, business_id, tracking_code, template_version, status, "
    "generated_at, approved_at, sent_at, delivered_at, "
    "transaction_id, rejection_reason"
)


def create_letter(business_id: int, tracking_code: str, template_version: str, pdf_bytes: bytes) -> int:
    """Create a new letter row for a business. Returns letter_id.

    Initial status is 'pending_review' — requires explicit approve_letter() before send.
    tracking_code must be globally unique (UNIQUE constraint enforced at DB).
    """
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO letters
                 (business_id, tracking_code, template_version, pdf_bytes, generated_at, status)
               VALUES (?, ?, ?, ?, ?, 'pending_review')""",
            (business_id, tracking_code, template_version, pdf_bytes, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


def get_letters(status: str = None, business_id: int = None) -> list[dict]:
    """List letters (metadata only — no PDF bytes). Filter by status and/or business_id."""
    query = f"SELECT {_LETTER_META_COLS} FROM letters WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if business_id is not None:
        query += " AND business_id=?"
        params.append(business_id)
    query += " ORDER BY generated_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_letter(letter_id: int) -> dict | None:
    """Fetch a single letter's metadata (no PDF bytes)."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {_LETTER_META_COLS} FROM letters WHERE id=?", (letter_id,),
        ).fetchone()
    return dict(row) if row else None


def get_letter_by_tracking_code(tracking_code: str) -> dict | None:
    """Lookup letter by its tracking code (e.g. 'VB01')."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {_LETTER_META_COLS} FROM letters WHERE tracking_code=?", (tracking_code,),
        ).fetchone()
    return dict(row) if row else None


def get_letter_pdf(letter_id: int) -> bytes | None:
    """Fetch the stored PDF bytes for a letter. Separate from metadata to keep list queries cheap."""
    with get_conn() as conn:
        row = conn.execute("SELECT pdf_bytes FROM letters WHERE id=?", (letter_id,)).fetchone()
    return row["pdf_bytes"] if row else None


def approve_letter(letter_id: int) -> bool:
    """Approve a pending_review letter. Idempotent-ish: no-op if already approved.
    Returns True if transition happened, False if letter wasn't in pending_review."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE letters
                 SET status='approved', approved_at=?
               WHERE id=? AND status='pending_review'""",
            (datetime.utcnow().isoformat(), letter_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def reject_letter(letter_id: int, reason: str) -> bool:
    """Reject a pending_review letter. Keeps row for audit; regeneration creates a new letter row."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE letters
                 SET status='rejected', rejection_reason=?
               WHERE id=? AND status='pending_review'""",
            (reason, letter_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_letter_sent(letter_id: int, transaction_id: str) -> bool:
    """Mark an approved letter as submitted to the print-API. Records transaction_id."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE letters
                 SET status='sent', sent_at=?, transaction_id=?
               WHERE id=? AND status='approved'""",
            (datetime.utcnow().isoformat(), transaction_id, letter_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_letter_failed(letter_id: int, reason: str) -> bool:
    """Mark a send attempt as failed (e.g. Letterxpress API returned error)."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE letters
                 SET status='failed', rejection_reason=?
               WHERE id=? AND status IN ('approved','pending_review')""",
            (reason, letter_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_letter_delivered(letter_id: int) -> bool:
    """Mark a sent letter as delivered (Letterxpress delivery confirmation, optional)."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE letters
                 SET status='delivered', delivered_at=?
               WHERE id=? AND status='sent'""",
            (datetime.utcnow().isoformat(), letter_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def retry_failed_letter(letter_id: int) -> bool:
    """Reset a 'failed' letter back to 'approved' so it can be re-sent.
    Clears the rejection_reason so the next failure doesn't leak the prior one."""
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE letters
                 SET status='approved', rejection_reason=NULL
               WHERE id=? AND status='failed'""",
            (letter_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


# ─────────────────────────────────────────────────────────────────
# Lander visits + status summary (2026-06-11 visit-tracking patch)
# ─────────────────────────────────────────────────────────────────


def record_lander_visit(tracking_code: str, user_agent: str = "", referer: str = "", ip_hash: str = ""):
    """One row per lander page load. Stray codes (bots probing /VB99) are
    logged too — the per-letter funnel joins FROM letters, so they only
    show up in totals, never in the letter table."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lander_visits (tracking_code, visited_at, user_agent, referer, ip_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (tracking_code, datetime.utcnow().isoformat(),
             (user_agent or "")[:250], (referer or "")[:250], ip_hash),
        )
        conn.commit()


def get_status_summary() -> dict:
    """Everything the /status cockpit needs in one call: lead + letter counts,
    the per-letter visit funnel, recent scans, and contact-form replies."""
    with get_conn() as conn:
        lead_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM businesses GROUP BY status ORDER BY n DESC"
        ).fetchall()
        letter_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM letters GROUP BY status"
        ).fetchall()
        per_letter = conn.execute("""
            SELECT l.tracking_code, l.status, l.sent_at, l.template_version,
                   COALESCE(b.name, '?') AS business,
                   COALESCE(v.n, 0) AS visits, v.first_visit, v.last_visit
              FROM letters l
              LEFT JOIN businesses b ON b.id = l.business_id
              LEFT JOIN (SELECT tracking_code, COUNT(*) AS n,
                                MIN(visited_at) AS first_visit,
                                MAX(visited_at) AS last_visit
                           FROM lander_visits GROUP BY tracking_code) v
                     ON v.tracking_code = l.tracking_code
             ORDER BY l.tracking_code
        """).fetchall()
        visits_total = conn.execute("SELECT COUNT(*) FROM lander_visits").fetchone()[0]
        recent_visits = conn.execute(
            "SELECT tracking_code, visited_at, user_agent, ip_hash "
            "FROM lander_visits ORDER BY visited_at DESC LIMIT 20"
        ).fetchall()
        replies_total = conn.execute("SELECT COUNT(*) FROM contact_submissions").fetchone()[0]
        replies = conn.execute(
            "SELECT name, email, phone, message, created_at "
            "FROM contact_submissions ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        customers = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE status='Customer'"
        ).fetchone()[0]
    return {
        "leads": {
            "total": sum(r["n"] for r in lead_rows),
            "by_status": {r["status"]: r["n"] for r in lead_rows},
        },
        "letters": {
            "total": sum(r["n"] for r in letter_rows),
            "by_status": {r["status"]: r["n"] for r in letter_rows},
            "per_letter": [dict(r) for r in per_letter],
        },
        "visits": {"total": visits_total, "recent": [dict(r) for r in recent_visits]},
        "replies": {"total": replies_total, "recent": [dict(r) for r in replies]},
        "customers": {"total": customers},
    }
