# 2026-04-23 — Google-scraping verifier is broken

## What broke

The `POST /businesses/{id}/verify` endpoint returned `has_website: false` for **28 of 28** verified Vorarlberg trades. Spot-check of 3 leads by Felix in a normal browser: **2 of 3 clearly had websites** (Hase & Kramer Möbelwerkstätte Dornbirn, Tischlerei Hartmann Schlins).

## Why

The verifier scrapes `https://www.google.com/search` from a Railway container. Google fingerprints cloud-datacenter IP ranges and serves them either (a) a cookie-consent interstitial, (b) a CAPTCHA page, or (c) a sparse results page with only Google-owned URLs. The regex then finds no non-directory domains → returns `has_website: false` for everyone.

## Impact if we'd trusted it

We'd have mailed ~40% of our 20-letter Phase 1 batch to businesses that already have websites. Wasted ~€8 in print-API fees. Worse: the pitch ("you have no website") is falsifiable in 10 seconds of Googling, so the reply rate tanks and we learn nothing about the real response rate for our actual target segment (truly website-less trades).

## How we worked around it

Manual spot-check for Phase 1 — Felix Googled the 28 candidates by hand (~10 min). Any business found with a real website was marked `status=Has Website` in the DB and excluded from the Phase 1 pool.

## Fix for Phase 2 (tracked as open task)

Options ranked by fit:

1. **Brave Search API** — free tier 2000 queries/month, deliberately developer-friendly, no datacenter blocking. Needs signup + API key.
2. **DuckDuckGo HTML** (`https://html.duckduckgo.com/html/`) — no API key, no rate limits per se, but HTML-scrape with same fragility as Google (DDG could change markup anytime). Doesn't block datacenter IPs currently.
3. **SerpAPI** — reliable but paid from query 1 (~$50/mo for 5k searches).

Recommendation: **Brave Search API**. Direct replacement of the `_check_website` function, ~30 lines of code, one env var (`BRAVE_API_KEY`). Free tier covers our foreseeable volume.

## Lesson

"Verified" is cheap to mark but expensive if wrong. Before trusting ANY automated check that touches a third party that might reject our IPs, we should manually cross-check ~3 results and fail loudly if the false-positive rate looks off.
