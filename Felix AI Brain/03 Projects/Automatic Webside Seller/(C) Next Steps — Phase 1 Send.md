# Next Steps — Phase 1 Send

> **Where we are (2026-05-05):** Infrastructure is live. `handwerkerweb.at/VBxx` → Railway lander → DB-tracked form submissions. Renderer produces 1-page PDFs with QR codes for all 8 Phase 1 leads (VB01–VB08). What's left: generate the letters into the DB, review, approve, send via Letterxpress, wait for replies.

> **Rule:** one step at a time. Don't jump ahead. Tell Claude when a step is done before moving to the next.

> **Note:** This doc supersedes the earlier 2026-04-24 version (which assumed `website-check.at`, fpdf2, and 4 letters). Current reality: `handwerkerweb.at`, WeasyPrint, 8 letters.

---

## What's already done (skip these)

- ✅ **Domain `handwerkerweb.at`** registered at world4you.
- ✅ **DNS** routed via Cloudflare (apex CNAME flattened to Railway origin).
- ✅ **SSL** auto-issued by Railway (Let's Encrypt).
- ✅ **Lander page** live at `https://handwerkerweb.at/VBxx` — serves form, posts to `/api/contact`, data lands in `contact_submissions` table.
- ✅ **Renderer** (WeasyPrint) produces 1-page PDFs for all 8 leads with QR codes pointing at `handwerkerweb.at/VB##`.
- ✅ **Telefon** in Absender block (`+43 676 6505015`).
- ✅ **Letterxpress account** signed up + KYC + funded (per Felix 2026-05-03).
- ✅ **DB schema** — `letters` table with status machine.
- ✅ **API endpoints** — `POST /api/letters/create`, `GET /api/letters`, `GET /api/letters/{id}/pdf`, `POST /api/letters/{id}/approve`, `POST /api/letters/{id}/reject`.
- ✅ **`generate-letters.py`** — local script that renders and uploads.

## The critical path — 6 steps to "letters are in the post"

Steps in order. Don't skip.

### Step 1 — Push sub-step 3 to Railway and smoke-test

**Why:** the new `/api/letters/*` endpoints need to be live before `generate-letters.py` can upload to them.

**What to do:**

```powershell
cd C:\Users\Felix\Desktop\business-finder

git add main.py generate-letters.py
git add "Felix AI Brain/03 Projects/Automatic Webside Seller/05 System/patches/2026-05-03-renderer/render_letter.py"
git add "Felix AI Brain/03 Projects/Automatic Webside Seller/05 System/patches/2026-05-05-generate-letters/"
git status                       # confirm only the intended files

git commit -m "feat: generate-letters.py + letter API endpoints (sub-step 3/5)"
git push
```

Wait ~60s for Railway to redeploy. Then smoke-test:

```powershell
$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:p3t5o1STv09bGJioKl6PJA"))
Invoke-RestMethod -Uri "https://handwerkerweb.at/api/letters" -Headers @{Authorization="Basic $cred"}
```

Expected: `{total: 0, rows: []}` (empty letters table — endpoints exist).

**Done when:** the GET returns 200 with that empty payload.

---

### Step 2 — Generate one letter and review

**Why:** before generating all 8, sanity-check that the upload path works end-to-end with a single lead.

**What to do:**

```powershell
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
python generate-letters.py --codes VB02
```

Expected output:
```
  OK    VB02  Tischlerei Brändle    letter_id=1  (22,xxx bytes)
Summary: 1 uploaded, 0 skipped, 0 dry-run, 0 failed.
```

Verify it landed:
```powershell
Invoke-RestMethod -Uri "https://handwerkerweb.at/api/letters" -Headers @{Authorization="Basic $cred"}
```

Should show one row with `tracking_code: VB02`, `status: pending_review`.

Open `letters/pending/VB02_Tischlerei_Braendle.pdf` in File Explorer. Verify:
- Recipient address sits inside where a DL window envelope would show
- Umlaute render correctly: `Brändle`, `Achstraße`
- Subject reads: `Eine Website für Tischlerei Brändle`
- QR code present beside the URL
- URL prints as `https://handwerkerweb.at/VB02`
- Signature gap present, name + email + phone at the bottom

**Bonus check — scan the QR with your phone.** Should open `handwerkerweb.at/VB02` and show the lander with "VB02" badge filled in. If you submit the form, a row should appear in `/api/contact/list` starting with `[Tracking: VB02]`.

**Done when:** the single PDF looks right + QR scans correctly.

**If anything's wrong:** STOP. Tell me what you saw. We fix the renderer/template before proceeding.

---

### Step 3 — Generate all 8 letters

**Why:** after Step 2's sanity check, we batch-generate the rest.

**What to do:**

```powershell
$env:AUTH_PASS = "p3t5o1STv09bGJioKl6PJA"
python generate-letters.py
```

Expected: `8 uploaded, 0 skipped, 0 failed`. (If you ran Step 2 already, expect `7 uploaded, 1 skipped` — VB02 is already in the DB and gets skipped.)

8 PDFs land in `letters/pending/`. Open each in File Explorer.

**Sanity-check VB06 specifically** (the one with the OSM mis-tag): the second paragraph must say `"Elektrotechniker"` — NOT `"Schlosser"`.

**Done when:** all 8 PDFs are visually correct.

---

### Step 4 — Approve / reject (sub-step 4 work)

**Why:** the `letters` table rows are still `pending_review`. Sub-step 5 (`send-approved.py`) only ships rows with `status='approved'`.

**What to do (after Claude writes sub-step 4):**

```powershell
# Approve all 8 (assuming all reviewed clean):
.\approve.ps1 -all

# Or approve specific codes only:
.\approve.ps1 VB01,VB02,VB04,VB05,VB07,VB08

# Or reject one with reason (e.g. if street number is wrong):
.\reject.ps1 VB03 -reason "street number wrong"
```

After approve: `GET /api/letters?status=approved` returns the approved rows.

**Done when:** the rows you want to send are `status='approved'`.

---

### Step 5 — Send via Letterxpress (sub-step 5 work)

**Why:** this is the actual mailing.

**What to do (after Claude writes sub-step 5):**

```powershell
# Dry-run first — prints what would be sent without calling the API:
$env:LETTERXPRESS_API_KEY = "..."
python send-approved.py --dry-run

# When dry-run looks correct, ship for real:
python send-approved.py
```

`send-approved.py` reads every `status='approved'` row from the `letters` table, POSTs each PDF + recipient address to Letterxpress's `/setJob` endpoint, records the transaction ID in the DB, and transitions `status` to `sent`.

**Budget for 8 letters:** ~€0.89 × 8 = €7.12 (already funded, you have €15 in the Letterxpress account).

**Done when:** `SELECT COUNT(*) FROM letters WHERE status='sent'` = 8.

---

### Step 6 — The 3–4 week wait

Don't iterate on the pitch during the response window. Postal is slow; let the signal develop.

**What to monitor (passive, 2 min/day):**
- `GET /api/contact/list` — form submissions, look for `[Tracking: VB##]` prefixes
- Email inbox — direct replies (some prospects will email instead of using the form)
- Phone — calls referencing a VBxx code (the letter prints the code prominently)
- Cloudflare Analytics — visit count per `/VBxx` URL (binary signal that the QR was scanned)

**What to do during the wait (parallel work, in priority order):**

1. **Decide hosting business model** — pick Model A, B, or C from `(C) Hosting Strategy.md`. Lock this before a first paying customer appears.
2. **Register as Kleinunternehmer (AT)** — free at the Finanzamt. Needed before signing the first contract.
3. **Commission AGB (€300–500)** — AT-based lawyer drafts contract terms with the suspension clause from the Hosting Strategy doc.
4. **Fix scraper's website-verifier** — replace the broken Google scraping (Brave Search API, see `08 Iteration Logs/(C) 2026-04-23 verifier broken.md`).
5. **Add business-existence verification** — cross-check OSM hits against Herold / Firmenbuch so we stop generating phantom leads.

---

## Phase 1 review — 3–4 weeks from send date

### What you'll have

- Per-letter visit counts (Cloudflare Analytics, even if no form submission)
- Form submissions and direct replies (email + phone)

### Decision gate

| Signal | Verdict | Next move |
|---|---|---|
| ≥ 1 reply (form, email, or phone) | **Phase 2 unlocked** | Scale to 50 letters with same pitch. Fix verifier + business-existence first so the 50-lead batch isn't full of phantoms. |
| 0 replies, ≥ 2 QR scans | Pitch works, CTA needs work | Iterate on the lander (not the letter). Re-test with another small batch. |
| 0 replies, 0 scans | Letter isn't landing | Iterate on the letter copy or segment. **Don't scale.** |

---

## Budget summary (Phase 1 total)

| Item | Cost |
|---|---|
| Domain (handwerkerweb.at, 1st year) | €12 |
| Cloudflare DNS / Pages | €0 |
| Letterxpress credit (€15 funded) | €15 |
| Letter postage (8 × €0.89) | ~€7.12 |
| **Total to get Phase 1 mailed** | **~€34.12** |

(Renewal cost from year 2 will be €36/yr at world4you — transferable to a cheaper registrar before the renewal date if Phase 1 produces signal.)

Meaningful money stuff (AGB, Kleinunternehmer) is Phase-2-gated — only spent if Phase 1 produces a signal.

---

## What I (Claude) will do as you progress

- **After Step 1 done:** I write sub-step 4 (`approve.ps1` + `reject.ps1`).
- **After Step 4 done:** I write sub-step 5 (`send-approved.py` + Letterxpress integration).
- **After Step 5 done:** I write a tiny `(C) 2026-05-XX send log.md` capturing the actual mail-out (date, transaction IDs, costs).
- **During the wait:** I'll only intervene when you ask. Phase 1 needs to breathe.

---

## What NOT to do during Phase 1

- Don't add more leads. 8 is enough to get a binary signal.
- Don't redesign the letter once mailed. We can't A/B test with n=8.
- Don't onboard a paying customer before AGB is signed and Kleinunternehmer registered. Even if VB02 says "ja, ich will eine Website" tomorrow, you respond with "vielen Dank, ich melde mich diese Woche mit dem Vertrag zurück" and stall 1–2 weeks while the legal scaffolding is built.

---

*Last updated: 2026-05-05 by Claude. This doc supersedes the 2026-04-24 version.*
