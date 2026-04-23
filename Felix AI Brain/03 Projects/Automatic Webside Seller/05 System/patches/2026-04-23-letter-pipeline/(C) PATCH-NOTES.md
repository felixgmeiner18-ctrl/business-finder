# Patch 2026-04-23 — Letter pipeline DB migration (sub-step 1 of 5)

## Goal

Lay the DB foundation for the letter send pipeline. New `letters` table tracks the full lifecycle of every letter (generated → reviewed → approved → sent → delivered). `businesses` table unchanged — no columns added, no existing data touched.

## Files changed (1)

- `database.py` — extended, +~160 lines (new table + 10 helper functions + PRIORITY_MAP additions)

Drop-in replacement lives next to this note.

## What changed

### New table: `letters`

```sql
CREATE TABLE letters (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id       INTEGER NOT NULL,
    tracking_code     TEXT NOT NULL UNIQUE,       -- e.g. "VB01"
    template_version  TEXT NOT NULL,              -- e.g. "v1"
    status            TEXT NOT NULL DEFAULT 'pending_review',
    pdf_bytes         BLOB,                        -- exact PDF Felix approved
    generated_at      TEXT NOT NULL,
    approved_at       TEXT,
    sent_at           TEXT,
    delivered_at      TEXT,
    transaction_id    TEXT,                        -- Letterxpress job ID
    rejection_reason  TEXT,
    FOREIGN KEY (business_id) REFERENCES businesses(id)
)
```

**Status machine:**

```
pending_review  ──approve──▶  approved  ──send──▶  sent  ──confirm──▶  delivered
      │                          │                   │
      ▼                          ▼                   ▼
   rejected                   failed              failed
```

Only transitions shown above are allowed. Helper functions enforce this with `WHERE status='<current>'` clauses — a bad call is a silent no-op (returns `False`), not a state corruption.

### New helper functions in `database.py`

| Function | Purpose |
|---|---|
| `create_letter(business_id, tracking_code, template_version, pdf_bytes)` | Insert a new letter row. Returns letter_id. |
| `get_letters(status=None, business_id=None)` | List metadata (no PDF bytes). |
| `get_letter(letter_id)` | Fetch one letter's metadata. |
| `get_letter_by_tracking_code(code)` | Lookup by tracking code (lander page handler will use this). |
| `get_letter_pdf(letter_id)` | Fetch the BLOB — only when actually needed (review UI, send script). |
| `approve_letter(letter_id)` | pending_review → approved. |
| `reject_letter(letter_id, reason)` | pending_review → rejected. |
| `mark_letter_sent(letter_id, transaction_id)` | approved → sent. |
| `mark_letter_failed(letter_id, reason)` | Any → failed (API error path). |
| `mark_letter_delivered(letter_id)` | sent → delivered. |

**Why PDF bytes are stored:** Felix's review approves *specific bytes*. If the template or merge logic changes between approve and send, we must ship exactly what Felix saw. BLOB in DB is the simplest way to guarantee that without a separate file-store.

**Why metadata-only list queries:** each PDF is ~50 KB. Listing 100 letters should not transfer 5 MB. `get_letters()` explicitly excludes `pdf_bytes`; `get_letter_pdf(id)` pulls bytes only when needed.

### PRIORITY_MAP additions

Added priority 3 for trades-niche categories that were missing: `heating_engineer`, `metal_construction`, `tiler`, `stonemason`, `plasterer`, `floorer`, `handyman`, `gasfitter`.

**Impact for Phase 1:** VB08 Ladurner (`metal_construction`) now scores priority 3 instead of 1. Cosmetic for Phase 1 — the 8 leads are already selected — but matters for Phase 2 filtering.

### Unchanged

- No columns added to `businesses`.
- Existing migration block untouched.
- `businesses` indices untouched.
- All existing functions (`upsert_business`, `get_businesses`, `update_business`, etc.) untouched.

## Backwards compatibility

- Existing 3,457 rows in `businesses` unaffected.
- `CREATE TABLE IF NOT EXISTS letters` on fresh startup creates the table on existing DBs without disturbing anything.
- Indices created with `IF NOT EXISTS` — idempotent.
- No breaking changes to any endpoint (this patch only touches `database.py`; `main.py` is unchanged).

## How to deploy

1. Copy `database.py` from this folder into `C:\dev\business-finder\`, replacing the original.
2. Review the diff:
   ```
   cd C:\dev\business-finder
   git diff database.py
   ```
   You should see additions only — PRIORITY_MAP extensions, a new `LETTER_STATUS_VALUES` set, the new `letters` CREATE TABLE + indices inside `init_db()`, and a block of 10 new helper functions at the bottom.
3. Commit + push:
   ```
   git add database.py
   git commit -m "feat: letters table + helper functions for send pipeline (sub-step 1/5)"
   git push
   ```
4. Railway auto-redeploys (~60s). Watch the deploy log — `init_db` will run on boot; the `letters` table is created on the existing Volume DB without touching existing data.
5. Verify:
   ```powershell
   $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:p3t5o1STv09bGJioKl6PJA"))
   # existing endpoint still works + still shows 3457 rows
   (Invoke-RestMethod -Uri "https://business-finder-production-87a6.up.railway.app/businesses?limit=1" -Headers @{Authorization="Basic $cred"}).total
   ```
   Expected: `3457`. If you get that, the migration ran clean.

## Rollback

`git revert HEAD && git push`. The new `letters` table sits empty and unreferenced — no harm leaving it in place either way, but revert cleanly reverses all code changes.

## What comes next (sub-step 2)

With the DB shape locked, sub-step 2 is the **HTML letter template + WeasyPrint integration**. That's a new file `letter_template.html` + a small Python helper that renders a PDF from a lead's fields. No `main.py` or `database.py` changes in sub-step 2 — it's pure new code, testable locally before it goes to Railway.
