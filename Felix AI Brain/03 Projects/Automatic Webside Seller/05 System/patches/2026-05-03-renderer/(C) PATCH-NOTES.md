# Patch 2026-05-03 — Letter PDF renderer (sub-step 2 of 5)

## Goal

Turn the locked Letter v1 copy + the 8 Phase 1 leads into actual PDFs we can hold up to the light. Pure new code — no DB changes, no Railway deploy needed, no API calls. This unblocks the **review** step of the send pipeline (Stage 2 in `(C) Letter Send Pipeline.md`).

## Files added (2)

- `letter_template.html` — Jinja2 HTML template, DIN 5008 Form B layout, A4 with window-envelope-aligned address block.
- `render_letter.py` — Python renderer (Jinja2 + WeasyPrint). Standalone, ~200 lines. No DB. Returns PDF bytes or writes to disk.

Both live in this patch folder. Drop-in copies will be added to the repo root in sub-step 3 (when `generate-letters.py` wires them to the DB).

## What you can do with it today

Render any of the 8 Phase 1 leads to a real PDF, locally, with one command:

```powershell
cd C:\Users\Felix\Desktop\business-finder\Felix AI Brain\03 Projects\Automatic Webside Seller\05 System\patches\2026-05-03-renderer
pip install weasyprint jinja2
python render_letter.py --self-test            # renders VB02 only
python render_letter.py                        # renders all 8
python render_letter.py --code VB06 --out C:\tmp\letters
```

PDFs land in `./out/{CODE}_{firma_slug}.pdf` by default.

## Layout decisions (and why)

| Choice | Why |
|---|---|
| **DIN 5008 Form B** (window-envelope address block at top:45mm, 85×45mm) | Standard German postal layout. Letterxpress envelopes use DL windows. Aligns without re-folding. |
| **Serif font (EB Garamond → Garamond → Georgia fallback)** | Letter v1 doc explicitly says "not Arial — looks less like spam". |
| **11pt body, 1.4 line-height, 2.4mm para gap** | Tight enough to fit name + contact line on one page after a 10mm signature gap. Tested: VB02 fits with margin. |
| **Tracking URL in monospace** | Visually marks it as "type this exactly" — distinguishes it from prose. |
| **Sender line above recipient (small grey, 7.5pt, underlined)** | DIN 5008 convention. Visible through the window above the recipient block. |
| **Subtle fold marks at 105mm and 210mm** (left margin, 4mm hairlines) | Helpful when folding into a DL envelope by hand. Letterxpress folds for us so this is decorative — but doesn't hurt. |

## Self-test invariants (automated)

`render_letter.py --self-test` asserts:

- PDF starts with `%PDF-` header
- Output size is sane (5–500 KB — typical 14–16 KB)
- Single page (no overflow to page 2)
- Extracted text contains: recipient firma, recipient street, PLZ+Ort, sender name, subject, kategorie label, price, tracking URL, sign-off, contact email

If any of these break in future template edits, the test fails loudly.

## Mail-merge variables (final list)

Filled at render time. All come from either the Lead dataclass or `Absender.from_env()`:

| Placeholder | Source |
|---|---|
| `{{ firma }}` | Lead |
| `{{ empfaenger_strasse }}` | Lead |
| `{{ empfaenger_plz }}` | Lead |
| `{{ empfaenger_ort }}` | Lead |
| `{{ kategorie_laie }}` | Mapped from Lead.kategorie via `KATEGORIE_LAIE_MAP`, with optional per-lead override (used for VB06 Hämmerle: OSM said `locksmith`, real category is `Elektrotechniker`) |
| `{{ absender_name / strasse / plz_ort / email / telefon }}` | env vars (`ABSENDER_*`) |
| `{{ ort_absender }}` | env var `ABSENDER_ORT` (default "Ludesch") |
| `{{ datum }}` | Today, formatted `DD.MM.YYYY` |
| `{{ region }}` | Static "Vorarlberg" |
| `{{ tracking_url }}` | Caller-supplied (e.g. `https://website-check.at/VB02`) |

## Env vars (sub-step 2 only — sub-step 3 will read from DB)

```
ABSENDER_NAME="Felix Gmeiner"
ABSENDER_STRASSE="Dorfstraße 41"
ABSENDER_PLZ_ORT="6713 Ludesch"
ABSENDER_EMAIL="felix.gmeiner18@gmail.com"
ABSENDER_TELEFON=""              # to be filled before live send
ABSENDER_ORT="Ludesch"           # used in the date line: "Ludesch, 03.05.2026"
TRACKING_DOMAIN="https://website-check.at"   # placeholder until domain bought
```

If `ABSENDER_TELEFON` is empty, the contact line shows email only. As soon as Felix provides a number, it's added to the line via env — no template change.

## Backwards compatibility

N/A — this is brand new code. Nothing existing was touched. `database.py`, `main.py`, `scraper.py` all unchanged.

## What this does NOT do (deliberate sub-step boundary)

- Does **not** read from the SQLite DB. Lead data is hardcoded in `PHASE_1_LEADS` for the self-test. Sub-step 3 (`generate-letters.py`) is the DB integration.
- Does **not** create rows in the `letters` table. Sub-step 3.
- Does **not** call Letterxpress. Sub-step 5 (`send-approved.py`).
- Does **not** track tracking-URL visits. That's the lander page, separate from this patch.

## How to verify (Felix manual review)

1. Run the renderer: `python render_letter.py` (after `pip install weasyprint jinja2`).
2. Open all 8 PDFs from `./out/`.
3. For each, check:
   - Recipient address visible in the top-left, would line up with a DL window envelope.
   - Umlaute (ß ä ö ü) render correctly — no `?` boxes.
   - The Kategorie word in the second paragraph matches what a layperson would call this trade (especially **VB06**: must say "Elektrotechniker", not "Schlosser").
   - Tracking URL ends in the correct code per letter.
   - Date is today's date.
   - Letter fits on one A4 page — no overflow.
4. If anything looks off, file the specifics in `08 Iteration Logs/` and we patch the template before sub-step 3.

## Sub-step 3 preview

Next file: `generate-letters.py` in the repo root. Responsibilities:

- Reads candidate leads from `businesses` table via `database.py` helpers.
- Generates `tracking_code` (format `VB{NN}`) for any lead that doesn't have one.
- Calls `render_letter.render_letter(lead, absender, tracking_url)` for each.
- Inserts a row into `letters` table with `pdf_bytes` BLOB and `status='pending_review'`.
- Writes a copy to `./letters/pending/{CODE}_{slug}.pdf` for visual review.

Felix's review step (Stage 2 in the pipeline doc) is unchanged — open the file, click approve.

## Rollback

Delete this folder. No system state was modified.
