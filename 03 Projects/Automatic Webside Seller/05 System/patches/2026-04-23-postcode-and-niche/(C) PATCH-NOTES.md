# Patch 2026-04-23 — Postcode capture + trades-only niche filter

## Goal

Enable the Automatic Webside Seller Phase 1 test: scrape **Vorarlberg trades only, with postal codes captured**, so we can actually address physical letters. Existing broad-search behaviour preserved.

## Files changed (3)

- `scraper.py` — extended, +90 lines
- `database.py` — extended, +12 lines
- `main.py` — extended, +18 lines

Complete replacement versions live next to this note. The raw unified diff is in `combined.patch`.

## What changed

### scraper.py
- New constant `TRADES_CRAFT_TAGS` — 16 OSM `craft` values counted as "Handwerker" (electrician, plumber, carpenter, painter, roofer, hvac, heating_engineer, tiler, glazier, locksmith, metal_construction, gasfitter, stonemason, plasterer, floorer, handyman).
- New `TRADES_QUERY_TEMPLATE` — narrower Overpass query that filters by `craft~"^({regex})$"` at source.
- New `_build_query(region, niche)` — returns trades template when `niche="trades"`, broad template otherwise.
- `_parse_tags` now pulls `addr:postcode` (falls back to `addr:postalcode`, then `contact:postalcode`), returned as `postcode`.
- `_parse_tags` reorders category fallback: `craft` is preferred before `shop/amenity/office` (trades are usually tagged `craft=...`).
- `search_businesses(region, niche=None)` — new optional param. For trades, phone is now **optional** (postal mail is the primary channel, don't drop leads that lack a phone). Dedup key switched from `(name, phone)` to `(name, phone, address)` to handle phone-less leads.

### database.py
- `businesses` table CREATE now includes `postal_code TEXT DEFAULT ''` and `phone` is now `DEFAULT ''` (was NOT NULL).
- Migration block adds `postal_code` column to existing tables — **safe on your live DB with 3,417 rows, existing data preserved**.
- `upsert_business(..., postal_code="")` — new optional param. When phone is empty, dedup falls back to `(name, postal_code, address)` so trades-only scrapes don't create duplicates.

### main.py
- `SearchPayload` + `QueuePayload` get optional `niche: str | None = None`.
- `run_search(region, niche=None)` and `run_queue(regions, niche=None)` thread it through.
- `POST /search` and `POST /search/queue` read `niche` from payload and pass to workers.

## Backwards compatibility

- Old `POST /search {"region": "..."}` calls with no niche still work exactly as before.
- Existing 3,417 rows preserved — migration only **adds** a column.
- Admin UI doesn't need changes for Phase 1 (you trigger the scrape via curl/PowerShell). UI niche toggle is a Phase 2 nice-to-have.

## How to deploy

1. Copy the three updated files from this folder into your local `business-finder` repo, replacing the originals.
2. Review the diff:
   ```
   git diff scraper.py database.py main.py
   ```
3. Commit:
   ```
   git add scraper.py database.py main.py
   git commit -m "feat: postcode capture + trades-only niche filter"
   git push
   ```
4. Railway auto-redeploys (~60s). Watch the deploy log for a clean boot (should see `init_db` run — migration adds `postal_code` column).
5. After redeploy is live, kick off the scrape:
   ```powershell
   $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:p3t5o1STv09bGJioKl6PJA"))
   Invoke-RestMethod -Method POST `
     -Uri "https://business-finder-production-87a6.up.railway.app/search" `
     -Headers @{Authorization="Basic $cred"; "Content-Type"="application/json"} `
     -Body '{"region": "Vorarlberg", "niche": "trades"}'
   ```
6. Poll status every 30s until `searching: false`:
   ```powershell
   Invoke-RestMethod -Uri "https://business-finder-production-87a6.up.railway.app/search/status" -Headers @{Authorization="Basic $cred"}
   ```
7. Expected: 60–120 seconds, ~100–400 trades leads added. Railway logs will print `[search] Vorarlberg niche=trades: N found, M new`.

## Next step after deploy

Query the clean trades subset:
```
GET /businesses?limit=500
```
Filter client-side (or add `?category=electrician` etc.) and count how many have full postal addresses. If ≥ 20 have `postal_code != ''` and a street address, Phase 1 letter test can start from this data.

## Rollback

If anything goes sideways: `git revert HEAD && git push`. The DB migration is additive-only (new column), so no rollback needed there — the column just sits unused.
