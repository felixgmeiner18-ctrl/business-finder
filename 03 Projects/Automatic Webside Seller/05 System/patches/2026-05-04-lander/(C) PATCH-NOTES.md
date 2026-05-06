# Patch 2026-05-04 — Lander page for `handwerkerweb.at/VBxx`

## Goal

Make the QR code on every Phase 1 letter actually lead somewhere. Without a live page at `handwerkerweb.at/VB02`, scanning the QR shows "Site not found" and the whole pitch dies. This patch ships a public lander that captures responses through the existing `/api/contact` pipeline — no new tables, no new endpoints.

## Files changed (3)

- `static/lander.html` — new. Mobile-first form (Firma · Name · Telefon · Beschreibung). Reads tracking code from URL path. Posts JSON to `/api/contact`.
- `main.py` — extended, +28 lines. New `GET /{code}` route, public-paths regex update, `/api/contact` validation relaxed (email now optional).
- (no `database.py` changes — uses existing `contact_submissions` table)

Drop-in replacements live in this patch folder.

## What changed

### `static/lander.html` (new)

A single self-contained HTML file. Serif font, calm palette, professional feel — designed to match the postal letter aesthetic so the trades-person doesn't feel a jarring transition from paper to web. Mobile-first (most QR scans happen on phone).

What the page does:
1. Reads the URL path on load. If it matches `^VB\d{2}$`, fills the visible "code" badge with it. Otherwise shows "(unbekannt)".
2. Renders the form: Firma, Name, Telefonnummer, Beschreibung.
3. On submit: POSTs JSON to `/api/contact` with the code embedded in the message field, e.g.
   ```
   [Tracking: VB02]
   Firma: Tischlerei Brändle
   Beschreibung: Wir machen Massivholzmöbel seit 1995.
   ```
4. Shows success (form hidden) or error (form re-enabled, phone fallback shown).

No external resources. No JS frameworks. ~9 KB. Loads fast on a 3G connection in a Vorarlberg basement.

### `main.py`

Three changes:

1. **`PUBLIC_PATH_PATTERN`** — new regex `^/VB\d{2}$` added next to existing `PUBLIC_PATHS` set.
2. **Middleware** — also checks the regex, so `/VB02` doesn't trigger Basic Auth.
3. **`POST /api/contact` relaxed** — email is no longer required. Validation is now:
   - `name` required
   - `message` required
   - `phone OR email` required (one of them must be present)
   This matches the letter promise (`nur Firma, Telefonnummer und zwei Sätze`).
4. **`GET /{code}`** — new route. Validates `code` matches `^VB\d{2}$` (raises 404 otherwise) and returns `static/lander.html`.

Route is declared at end of file → won't shadow any existing route. Other path patterns (`/admin`, `/api/...`, `/businesses/{id}`) take precedence because they're declared first AND because `code` here is just a single segment.

### Backwards compatibility

- All existing routes untouched.
- `/api/contact` accepts every payload it accepted before (now also accepts `email=""`).
- No DB migration needed.
- No env vars changed.
- `contact_submissions` table grows the same way it did before — Phase 1 lander rows will be identifiable by `[Tracking: VB##]` prefix in their `message` column.

## Smoke tests (passed locally 2026-05-04)

| Test | Expected | Result |
|---|---|---|
| `GET /VB02` | 200, serves lander.html, no auth required | ✓ 200 |
| `GET /VBaa` (invalid code) | 401 (middleware blocks), would be 404 if past auth | ✓ 401 |
| `GET /admin` | 401 (requires Basic Auth) | ✓ 401 |
| `POST /api/contact` with empty email | 200, `{ok:true}` | ✓ 200 |
| `POST /api/contact` with empty phone AND empty email | 400 | passes by code inspection |

## How to deploy

Done in 3 steps. Steps 1–2 are local + git. Step 3 is the DNS surgery — most of the work is on Felix's side at world4you and Railway dashboards.

### Step 1 — Drop replacement files into the repo

Copy these from this patch folder into `C:\Users\Felix\Desktop\business-finder\`:
- `lander.html` → `static/lander.html`
- `main.py` (full file with the diff applied — see this folder)

(The renderer / template changes from the 2026-05-03 patch are already in place from the previous session.)

### Step 2 — Commit + push

```powershell
cd C:\Users\Felix\Desktop\business-finder
git add static/lander.html main.py
git commit -m "feat: lander page for letter tracking codes (sub-step 2.5)"
git push
```

Railway auto-redeploys (~60s). Watch the deploy log; should boot cleanly.

### Step 3 — Verify the lander before DNS pointing

While the domain is still parked at world4you, you can already test the lander on the existing Railway URL:

```powershell
# This should return 200 with the lander HTML
$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:p3t5o1STv09bGJioKl6PJA"))
curl https://business-finder-production-87a6.up.railway.app/VB02
# (no auth header needed for /VBxx — public)
```

Open `https://business-finder-production-87a6.up.railway.app/VB02` in your browser. You should see the lander with code "VB02" badge filled in, the form rendered, and the styling looking right. Try submitting the form — should show "Vielen Dank!" and you should see a row in the admin contact submissions list.

### Step 4 — Connect handwerkerweb.at to Railway

Two ends to wire — Railway adds the custom domain, then world4you points its DNS records there.

**At Railway (~3 min):**

1. Open Railway dashboard → your `business-finder` project → service `business-finder` → **Settings** → **Domains**.
2. Click **Custom Domain**. Enter `handwerkerweb.at` and click Add. Then add `www.handwerkerweb.at` too.
3. Railway shows you a CNAME target like `xxx-xxx-xxx.up.railway.app` for each domain. **Copy these strings** — you need them in step 5.
4. Don't worry that Railway shows "Pending Configuration" — that's expected until DNS propagates.

**At world4you (~5 min):**

5. Log into `my.world4you.com` → **Domains** → click `handwerkerweb.at` → **DNS-Einstellungen** (or "DNS-Manager").
6. Delete any default A or CNAME records pointing to a parking page (don't delete NS or SOA records).
7. Add records:
   - **Type CNAME**, Name `www`, Value: `<railway-cname-target-for-www>`, TTL default.
   - **Type ALIAS** or **ANAME** (if available) on the apex `handwerkerweb.at`, Value: `<railway-cname-target-for-apex>`. If world4you only supports A records on the apex, use Railway's IP-based "A record" option instead — Railway shows both options on its custom domains page.
8. Save. world4you typically propagates within 5–60 minutes (TTL-dependent).

**Verify:**

9. After 10–15 min, run:
   ```powershell
   nslookup handwerkerweb.at
   nslookup www.handwerkerweb.at
   ```
   Both should resolve to a `.railway.app` host or Railway IP.
10. Visit `https://handwerkerweb.at/VB02` in a browser. Should show the lander, certificate valid, code "VB02" badge filled in.

If step 10 works → letters can be mailed safely. If not, check the Railway dashboard "Domains" tab for the specific error (usually DNS hasn't propagated yet, or the CNAME target was mistyped).

## What this does NOT do (deliberate sub-step boundary)

- Does **not** track per-letter visit counts. We see *if* a letter got a reply (a row in `contact_submissions` with the matching VB code), not *how many times* the QR was scanned without submitting. For Phase 1's gate (≥3% reply rate on 8 letters = ≥1 reply), the binary "did anyone reply" signal is enough. Visit logging is a Phase 2 add.
- Does **not** auto-link the lander reply to the `letters` table. The link is the tracking code in the message text. Sub-step 3 (`generate-letters.py`) and sub-step 4 (review UI) will tighten this when needed.
- Does **not** send Felix a notification email when a lead submits. He'll see it via the admin dashboard, or — better — we add a tiny notify-me hook in a follow-up patch (5 lines, `httpx.post` to a webhook).

## Rollback

`git revert HEAD && git push`. Railway redeploys in ~60s. Lander disappears. Existing system unaffected.

## What comes next

**Sub-step 3** — `generate-letters.py`. DB-integrated letter generator that:
- Reads candidate leads from the `businesses` table (`status='New'` AND `letter_status IS NULL`).
- Allocates the next free `tracking_code` (`VB{NN}` zero-padded, advancing past existing codes).
- Calls `render_letter.render_letter(...)` to produce PDF bytes.
- Inserts row into the `letters` table with `pdf_bytes` BLOB and `status='pending_review'`.
- Mirrors PDF to `letters/pending/{CODE}_{slug}.pdf` for visual review.

This unblocks sub-step 4 (`approve.ps1` / `reject.ps1`) and sub-step 5 (`send-approved.py` calling Letterxpress).
