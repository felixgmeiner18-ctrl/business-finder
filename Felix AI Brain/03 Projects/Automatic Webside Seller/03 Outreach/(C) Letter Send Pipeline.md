# Letter Send Pipeline — Phase 1

> **Locked:** 2026-04-23
> **Print-API:** Letterxpress (picked 2026-04-23, pending Felix approval)
> **Human-in-the-loop:** Felix reviews every PDF before it reaches the print-API. No exceptions.

## Print-API decision — Letterxpress

| Criterion | Letterxpress | Pingen | Ö-Post Geschäftskunde |
|---|---|---|---|
| AT-domestic price (1pg B&W) | ~€0.89 | ~€1.25 | ~€0.60 at volume |
| Billing currency | EUR | CHF | EUR |
| Private-individual account | ✅ yes | ✅ yes | ❌ requires Gewerbe |
| REST API quality | Mature | Mature | Limited / portal-first |
| KYC onboarding | ID upload, ~1 day | ID upload, ~1 day | Gewerbeschein + contract |
| DE/CH support for later | ✅ | ✅ | DE via partner, pricey |
| Phase 1 blocker? | No | No | **Yes** (no business yet) |

**Pick:** Letterxpress. Cheapest of the two that can onboard us today, EUR-billed, reuses for DE expansion later. Revisit Ö-Post once Kleinunternehmer registration is done — at scale (500+ letters/month) the price delta becomes material.

## Account setup (Felix)

1. Sign up at letterxpress.de as private individual.
2. KYC: upload photo of Personalausweis (front + back). Approval usually within 24h.
3. Fund the account via bank transfer — prepaid balance model, no subscription.
4. Generate API key in account settings. Store as `LETTERXPRESS_API_KEY` env var.
5. Note your `username` (account login) — also needed for API auth.

**Fund amount for Phase 1:** €15. Covers 8 letters at €0.89 each (€7.12) plus margin for any reprints or test letters during development.

## Pipeline architecture

Three scripts. Each stage is explicit and manual — no silent send.

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Stage 1        │      │  Stage 2        │      │  Stage 3        │
│  GENERATE       │ ───▶ │  REVIEW         │ ───▶ │  SEND           │
│  (Python)       │      │  (Felix manual) │      │  (Python)       │
└─────────────────┘      └─────────────────┘      └─────────────────┘
   generate-               approve.ps1 /             send-approved.py
   letters.py              File Explorer
```

### Stage 1 — Generate

**Script:** `generate-letters.py`

**Inputs:**
- Leads from DB where `status = 'New'` AND `letter_status = 'new'` (or explicit IDs passed as args)
- Letter template (`(C) Letter v1 — DE Trades.md` → Jinja/Python format string)
- Absender details (env vars: `ABSENDER_NAME`, `ABSENDER_STRASSE`, `ABSENDER_PLZ_ORT`, `ABSENDER_EMAIL`, `ABSENDER_TELEFON`)
- Tracking domain + per-letter code (DB column `tracking_code`)

**Outputs:**
- One PDF per lead at `./letters/pending/{CODE}_{FirmaSlug}.pdf`
  - E.g. `letters/pending/VB01_Benzer_Schlosserei.pdf`
- DB update: `letter_status = 'pending_review'`, `generated_at = now()`

**PDF engine:** WeasyPrint (HTML+CSS → PDF). Letter body is an HTML file with DIN 5008 layout, merge fields filled via Python. WeasyPrint produces postable-quality PDFs for free.

### Stage 2 — Review (Felix)

**No code, no UI. Just files and eyes.**

1. Open `C:\dev\business-finder\letters\pending\` in File Explorer.
2. Open each PDF (Adobe Reader / Chrome). Check:
   - Recipient name + address correct and readable
   - Kategorie word in the hook is right (e.g. "Elektrotechniker" not "Schlosser" for VB06)
   - No mangled characters (ß, ä, ö, ü render correctly)
   - Tracking URL ends in the correct code
   - Absender block is complete
3. Approve or flag:
   - **All good:** run `.\approve.ps1 -all` — marks all pending_review rows as `approved`.
   - **Some bad:** run `.\approve.ps1 VB01,VB02,VB04,VB07,VB08` — approves only listed codes. The rest stay pending.
   - **Specific reject:** run `.\reject.ps1 VB03 -reason "street number wrong"` — logs reason, moves PDF to `./letters/rejected/`, row goes back to `letter_status = 'new'` for fix + regenerate.

Review time per letter: ~30 seconds. 8 letters = 4 minutes.

### Stage 3 — Send

**Script:** `send-approved.py`

**What it does:**
1. Queries DB for rows where `letter_status = 'approved'`.
2. For each row:
   - Reads PDF from `./letters/pending/`.
   - POSTs to Letterxpress API (`/setJob` endpoint) with PDF + recipient address + options (color=b/w, delivery=normal).
   - Records transaction ID in DB.
   - Updates `letter_status = 'sent'`, `sent_at = now()`.
   - Moves PDF to `./letters/sent/{CODE}_{FirmaSlug}.pdf`.
3. Prints summary: `Sent N of N. Failed: M.`

**Safety:** Dry-run mode (`--dry-run`) available for the first live run — prints what would be sent without actually calling the API.

## DB changes required

Add to `businesses` table:

```sql
ALTER TABLE businesses ADD COLUMN letter_status TEXT DEFAULT 'new';
ALTER TABLE businesses ADD COLUMN tracking_code TEXT;
ALTER TABLE businesses ADD COLUMN letter_generated_at TEXT;
ALTER TABLE businesses ADD COLUMN letter_approved_at TEXT;
ALTER TABLE businesses ADD COLUMN letter_sent_at TEXT;
ALTER TABLE businesses ADD COLUMN letter_delivered_at TEXT;
ALTER TABLE businesses ADD COLUMN letter_transaction_id TEXT;
ALTER TABLE businesses ADD COLUMN letter_template_version TEXT;
```

`letter_status` values: `new` | `pending_review` | `approved` | `sent` | `delivered` | `failed` | `rejected`

## Phase 1 execution plan (the actual 8-letter run)

Ordered, blocking dependencies noted.

1. [Felix] Sign up Letterxpress + KYC + fund €15.
2. [Felix] Buy tracking domain (`website-check.at` or similar — see separate doc).
3. [Felix] Stand up minimal lander at `{domain}/VBxx` (Cloudflare Pages + form).
4. [Felix] Confirm Absender address (full street in Ludesch).
5. [Claude] Write `generate-letters.py`, `send-approved.py`, `approve.ps1`, `reject.ps1`.
6. [Claude] Add `letter_*` columns to DB via migration.
7. [Claude] Write letter HTML template for WeasyPrint (DIN 5008 compliant).
8. [Felix+Claude] Run generate-letters.py for the 8 IDs — test-preview.
9. [Felix] Review all 8 PDFs carefully.
10. [Felix] Approve what looks good.
11. [Claude] Run `send-approved.py --dry-run` — verify API call shape.
12. [Felix] Green-light live send.
13. [Claude] Run `send-approved.py` for real.
14. Wait 3–4 weeks. Track lander visits + any replies (phone/email).
15. Phase 1 review: response rate vs gate (≥ 3%).

## Phase 2 — when we grow out of this

At ~50+ letters/week, manual File Explorer review becomes the bottleneck. Phase 2 moves review into the admin UI already on Railway:

- New `/letters/pending` route — lists PDFs with inline preview (PDF.js).
- Approve / reject buttons per letter.
- "Send all approved" button.
- Rejection workflow: enter fix reason, letter re-enters generation queue.

Same underlying pipeline. Only the review UI changes. No breaking rewrite.

## What will NOT happen

- No letter ever goes directly from the generator to Letterxpress.
- No batch send without `letter_status = 'approved'` for each row.
- No automated re-send without explicit re-approval.
- No hidden `auto_approve` flag.
