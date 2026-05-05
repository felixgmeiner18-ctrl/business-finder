# Patch 2026-05-05 — generate-letters.py + letter API endpoints (sub-step 3 of 5)

## Goal

Wire the renderer (sub-step 2) to the `letters` table (sub-step 1 migration). After this patch, running one command produces 8 reviewable PDFs locally **and** registers them in the Railway DB with `status='pending_review'`. That unblocks the approve/reject step (sub-step 4) and the Letterxpress send (sub-step 5).

## Files added / changed (3)

- **`main.py`** — extended, +110 lines. Imports 6 letter helpers from `database.py`. Adds 2 Pydantic models and 5 admin-only endpoints under `/api/letters/...`.
- **`generate-letters.py`** — new file in repo root, ~200 lines. Local script. Renders Phase 1 PDFs, uploads them to Railway via the new endpoint, mirrors to `letters/pending/` for File Explorer review.
- **`Felix AI Brain/.../patches/2026-05-03-renderer/render_letter.py`** — extended `Lead` dataclass with optional `business_id`. `PHASE_1_LEADS` now carries the 8 IDs from `(C) Phase 1 Send List.md`.

## What changed

### `main.py` — 5 new endpoints

All admin-only (Basic Auth). Path-routing follows the existing pattern.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/letters/create` | Insert a new letter row from a freshly-rendered PDF. Body: `{business_id, tracking_code, template_version, pdf_bytes_b64}`. Validates the tracking code matches `^VB\d{2}$`, checks the business exists, decodes the base64 PDF, sanity-checks the `%PDF-` header, rejects payloads >2 MB. Returns `{letter_id, tracking_code, status:"pending_review", pdf_bytes}`. **409** on tracking-code collision (UNIQUE in DB). |
| GET | `/api/letters` | List letters newest-first. Query params: `status`, `business_id`. Returns metadata only — no BLOB. |
| GET | `/api/letters/{id}/pdf` | Download a single letter's PDF (raw bytes, `application/pdf`). |
| POST | `/api/letters/{id}/approve` | `pending_review → approved`. **409** if the letter is in any other state. |
| POST | `/api/letters/{id}/reject` | `pending_review → rejected`. Body: `{reason}`. Reason is logged to the row. |

The endpoints are surgical wrappers around the existing `database.py` helpers from the 2026-04-23 letter-pipeline patch — no new business logic, just HTTP exposure.

### `generate-letters.py` — what it does

1. Reads `PHASE_1_LEADS` from `render_letter.py` (the 8 manually-curated leads).
2. For each lead:
   1. Renders the PDF (template v1, today's date, `https://handwerkerweb.at/VB##` tracking URL).
   2. Writes the PDF to `letters/pending/{CODE}_{slug}.pdf` for Felix to review in File Explorer.
   3. POSTs the PDF (base64) + metadata to `https://handwerkerweb.at/api/letters/create`.
3. Prints a summary: `N uploaded, M skipped (already exists), K failed`.

Idempotent: if you run it twice, the second run gets 409 Conflict from the server (UNIQUE constraint on `tracking_code`) and prints `SKIP` for each existing code. No duplicates, no clobber.

`--dry-run` renders PDFs locally without uploading. Useful for previewing without touching the DB.
`--codes VB02,VB06` re-renders specific leads only.

### `render_letter.py` — Lead.business_id

Optional field added to the `Lead` dataclass. The 8 entries in `PHASE_1_LEADS` now carry their `business_id` (from `(C) Phase 1 Send List.md`):

```
VB01 → 3454   VB05 → 3435
VB02 → 3448   VB06 → 3424
VB03 → 3446   VB07 → 3419
VB04 → 3445   VB08 → 3455
```

## Backwards compatibility

- All existing routes untouched.
- `Lead.business_id` is optional → existing code that constructs `Lead` without it still works.
- No DB migration required (table was created in the 2026-04-23 letter-pipeline patch).
- `letters` table grows with one row per upload — first time it gets data.

## Smoke tests

### Local (no Railway needed) — dry-run

```powershell
cd C:\Users\Felix\Desktop\business-finder
python generate-letters.py --dry-run --codes VB02
```

Expected: 1 PDF appears at `letters/pending/VB02_Tischlerei_Braendle.pdf`. Output ends with `1 dry-run, 0 failed`.

### Live — single letter

```powershell
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
python generate-letters.py --codes VB02
```

Expected:
- One row in `letters` table with `tracking_code='VB02'`, `status='pending_review'`, BLOB present.
- `GET /api/letters?status=pending_review` returns this row.
- `GET /api/letters/{id}/pdf` opens the same PDF in the browser.
- Re-running the same command prints `SKIP VB02 ('VB02' already exists)`.

### Live — full Phase 1 batch

```powershell
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
python generate-letters.py
```

Expected: `8 uploaded, 0 skipped, 0 failed`.

## How to deploy

1. Push the 3 changed files:
   ```powershell
   cd C:\Users\Felix\Desktop\business-finder
   git add main.py generate-letters.py "Felix AI Brain/03 Projects/Automatic Webside Seller/05 System/patches/2026-05-03-renderer/render_letter.py"
   git add "Felix AI Brain/03 Projects/Automatic Webside Seller/05 System/patches/2026-05-05-generate-letters/"
   git commit -m "feat: generate-letters.py + letter API endpoints (sub-step 3/5)"
   git push
   ```
2. Wait ~60s for Railway to redeploy.
3. Verify the endpoints exist:
   ```powershell
   $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:p3t5o1STv09bGJioKl6PJA"))
   Invoke-RestMethod -Uri "https://handwerkerweb.at/api/letters" -Headers @{Authorization="Basic $cred"}
   ```
   Expected: `{total: 0, rows: []}` (empty until generate-letters runs).
4. Run the live smoke test (see above) for VB02 first. If it lands cleanly, run the full batch.

## What this does NOT do

- **Does not send any letters.** Letters land in `pending_review` only. Sub-step 5 (`send-approved.py`) reads `status='approved'` rows and submits to Letterxpress — out of scope here.
- **Does not generate from the `businesses` table directly.** Phase 1 uses the manually-curated `PHASE_1_LEADS`. Phase 2 will add a `businesses` → `Lead` parser once the address parsing + Google verifier rebuild is done.
- **Does not provide an admin UI for review.** Review is File Explorer + the new `/api/letters/{id}/approve` endpoint (called via the upcoming `approve.ps1` in sub-step 4).

## What comes next — sub-step 4 (approve / reject)

`approve.ps1` and `reject.ps1` — small PowerShell scripts that:
- `.\approve.ps1 -all` calls `POST /api/letters/{id}/approve` for every pending_review row.
- `.\approve.ps1 VB01,VB02,VB04` approves only the listed codes.
- `.\reject.ps1 VB03 -reason "street number wrong"` rejects + logs reason.

After sub-step 4, the workflow is: render → review PDFs in File Explorer → approve or reject by code → state in Railway DB updates → ready for send-approved.py.

## Rollback

`git revert HEAD && git push`. The `letters` table rows that `generate-letters.py` already inserted stay in the DB but become unreachable from the (rolled-back) endpoints. They can be left in place (audit trail) or `DELETE FROM letters WHERE tracking_code LIKE 'VB%'` cleared via a one-off shell.
