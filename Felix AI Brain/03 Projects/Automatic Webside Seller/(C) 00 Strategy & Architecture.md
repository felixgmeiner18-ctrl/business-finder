# (C) 00 Strategy & Architecture

> **Status:** Locked 2026-04-23. First strategic pass. Overrides nothing in `CLAUDE.md` — just concretizes decisions left open there.

## The one architectural truth

**Cold email to DACH trades is effectively illegal at scale** (UWG §7, GDPR, UCA Art. 3(1)(o)). The outreach channel is therefore the keystone of the whole pipeline — not a detail to resolve later. Every upstream decision (scraper fields, qualification rules) and downstream decision (fulfillment speed) is shaped by it.

## Decisions locked (2026-04-23)

- **Outreach channel (Phase 1 test):** Postal mail via print-API (Pingen / Letterxpress / alternative — TBD).
  - Legal: yes. Automatable: yes (API-driven). Cost: ~€1/letter. Fits DACH trades' older demographic.
- **Geography:** Austria first (Felix lives in Ludesch, Vorarlberg). **Phase 1 target: all of Vorarlberg** (~400k inhabitants, 4 Bezirke, expected 300–800 trades without website). DE + CH in later waves.
- **Niche:** Trades — plumbers, electricians, HVAC, handymen. Locked per `CLAUDE.md`.
- **Tech stack:** Python (Scrapy/Playwright for scraping, SQLite for state, FastAPI or plain CLI for services).
- **Budget:** €30–100 / month. Enough for 30–80 letters in Phase 1 test + small SaaS fees. No ad budget.

## Three-phase plan (do not skip Phase 1)

### Phase 1 — De-risk outreach (1–2 weeks, mostly manual)

The goal of Phase 1 is **a number**: response rate to ~20 physical letters. Everything else is subordinate.

1. Audit existing scraper → understand current output.
2. Export ~20 qualified leads from existing scraper data (one niche, one city).
3. Draft letter v1 in DE (hook / proof / offer / CTA with unique tracking URL).
4. Open print-API account (Pingen or Letterxpress).
5. Send letters. Log everything.
6. Measure response rate. Gate for Phase 2: ≥ 3% response. If lower → iterate copy/targeting before automating.

### Phase 2 — Wire the pipeline (only if Phase 1 gates pass)

Each stage = one Python module with a clear input/output contract, reading/writing a central SQLite DB (`05 System/pipeline.db`). State transitions move leads between folders/statuses.

```
  scrape        qualify        outreach        track           fulfill
    │              │              │              │                │
    ▼              ▼              ▼              ▼                ▼
 01 Leads   →   02 Qualified → 03 Outreach → 03 Outreach ←→   04 Fulfillment
 (raw)          (filtered)      (sent)       (replied)         (paying)
```

- **Scraper service** — runs nightly on the Ryzen box. Idempotent (no duplicate leads).
- **Qualifier** — applies hard filters + soft score, promotes leads to `02 Qualified`.
- **Outreach sender** — daily batch: picks N qualified leads, mail-merges letter, submits to print-API, marks lead as `sent`.
- **Response tracker** — unique tracking URL per letter → logs opens / replies. Manual phone replies logged via a short form.
- **Cron/systemd** — nightly scrape, daily outreach batch.

### Phase 3 — Template fulfillment (only after Phase 2 produces replies)

- Single Astro or Next.js template (5 sections: hero, services, reviews, about, contact).
- Customer intake form → JSON → template filled → Vercel deploy → domain registered (Cloudflare API).
- Stripe payment link (€500–1500 one-time).
- SLA: 72h from payment to live site.

## Lead schema (draft — finalizes during Phase 2 design)

| Field | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| business_name | str | required |
| owner_name | str | optional — if extractable from GBP/Impressum |
| street, city, zip, country | str | required for postal outreach |
| phone | str | optional — secondary CTA |
| email | str | optional — not used for Phase 1 |
| niche | enum | plumber / electrician / hvac / handyman |
| gbp_url | str | source of truth that they're still active |
| has_website | bool | must be false to enter pipeline |
| source | str | scraper module that found them |
| scraped_at | timestamp |  |
| status | enum | raw / qualified / sent / replied / rejected / customer |
| tracking_slug | str | unique short code for letter tracking |

## Legal guardrails (Phase 1)

- **Postal mail is legal** for B2B solicitation in DE/AT/CH — no opt-in needed.
- **Imprint check:** Do NOT scrape sites that explicitly forbid commercial use in their Impressum/Terms.
- **Kleinunternehmer / Impressum:** before first paying customer, Felix's side-business must have a legal form compatible with apprentice status (likely Kleinunternehmer in DE/AT, or equivalent).
- **Data retention:** scraped addresses are business contact data (GDPR Art. 6(1)(f) legitimate interest for B2B is defensible for postal outreach). Delete after rejection.

## Open questions (will answer as they become blocking)

- Print-API winner: Pingen vs Letterxpress vs alternative.
- Tracking slug → lander page: simple static site on Cloudflare Pages with form.
- Unique phone number for each letter: expensive; skip for Phase 1, aggregate via one number + "mention the code" ask.
- Domain for the lander: buy something forgettable but trustworthy.

---

## Scraper audit — `business-finder` repo (2026-04-23)

**Verdict:** Far more than "rough". This is ~70% of the end-to-end pipeline already built. Strategy shifts from "build from scratch" to **"extend existing system for postal outreach"**. Saves weeks.

### What's already there

- **`scraper.py`** — Uses OpenStreetMap Overpass API (free, no API key, no rate limits). Query finds any business with phone but no website/url tags in a given region. Returns: `name, phone, email, address, category, has_website`. Multi-endpoint failover built in.
- **`database.py`** — SQLite with `businesses` table, indices, priority scoring map (1–5 per category), status workflow (`New` / `Has Website` / custom), CRUD, settings table, contact_submissions table. Idempotent upsert on `(name, phone)`.
- **`main.py`** — FastAPI backend with: HTTP Basic Auth, single/queued region search, search status polling, website re-verification via Google scraping (to catch leads who got a site since scrape), **AI email drafter with category-specific German hooks**, **Claude-based website generator** producing full themed specs (colors, fonts, layouts, German copy), ZIP export of generated sites, public contact form.
- **Frontend** — `portfolio.html` (public agency site), `index.html` (admin dashboard), `generator.html` (website preview/editor).
- **Deploy** — Railway-ready via `railway.toml`, runs on uvicorn.
- **Secret weapon:** the website generator uses claude-opus-4-6 to produce genuinely custom-looking sites per business. This solves ~70% of the fulfillment problem before we even start Phase 3.

### Gaps we must close for postal outreach

| Gap | Why it matters | Fix |
|---|---|---|
| No postcode captured | Can't address a letter without PLZ | Add `addr:postcode` to `_parse_tags` + `postal_code` column |
| No owner name | Personalized letters convert 2–3× better (`Herrn Müller` beats generic) | Optional Stage 2 Impressum scrape — skip for Phase 1 test |
| No letter-send tracking | Can't measure Phase 1 gate (response rate) | Add `letter_sent_at`, `letter_template_version`, `tracking_slug` columns |
| No print-API integration | That IS the outreach sender | New `letter_sender.py` module |
| No tracking landing page | Response rate measurement | Static one-pager at e.g. `website-check.de/[slug]` logging visits |
| Category filter is a soft priority, not a hard gate | We want trades-only in Phase 1 | Add niche filter at qualification stage |

### Mismatch: system was built for cold email

The existing `draft-email` endpoint and category hooks assumed cold email outreach — which we've ruled out as legally dead. Don't delete it; **park it** for potential future use on warm leads (inbound via lander form). For now, all outreach wiring points at postal.

### Architecture decision: keep and extend

- **Keep:** FastAPI structure, SQLite, admin UI, website generator, priority scoring, OSM scraper.
- **Extend:** add postcode, letter-tracking columns; add `letter_sender.py`; add lander page; add `/businesses/{id}/send-letter` endpoint.
- **Deploy:** keep Railway for the UI/DB (Felix can check leads from any device during his day), but run the scraper locally on the Ryzen box on schedule to avoid Railway's egress/CPU limits. DB either shared via Railway Postgres later, or scrape → export → sync.

### Unknowns — need Felix to confirm

1. **Is `businesses.db` already populated with real leads**, or is it fresh? If populated, we can test-qualify immediately without re-scraping. If fresh, Phase 1 starts with a scrape run for 1–2 target cities.
2. **Railway deploy status** — is it live? URL? Credentials for Basic Auth?
3. **ANTHROPIC_API_KEY configured on Railway?** Needed for the generator to work; not needed for Phase 1 letter test.

## What we do next (revised)

Phase 1 is now much cheaper than expected. Revised order:

1. **Felix confirms DB state + Railway status** (answer the 3 unknowns above).
2. **Extend schema** — add `postal_code`, `letter_sent_at`, `letter_template_version`, `tracking_slug` + migration.
3. **Extend scraper** — capture `addr:postcode`.
4. **Define qualification filter** — SQL query that pulls "trades-only, has full address, priority ≥ 3, status = New". Output: a list of ≤ 20 candidates.
5. **Parallel:** pick print-API + draft letter v1.
6. **Send 20 letters, log tracking, measure response.**

Task list in TaskList reflects this. Task #7 (audit) is done after this update lands.

---

*This document is the source of truth for the project's architecture. Update (or supersede with a dated `(C) 01 ...` doc) when strategy changes.*
