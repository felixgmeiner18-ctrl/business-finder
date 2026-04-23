# Automatic Webside Seller

An automated lead-to-sale pipeline that finds small businesses without a website, qualifies them, pitches them a website, and fulfills the sale — all with as little manual work from me as possible. The scraper already exists in rough form. The rest of the machine needs to be built, connected, and left to run on its own. The goal isn't a hobby project — it's the first real income stream outside my apprenticeship.

## Claude's Role

Claude is my co-architect on this pipeline. Not a sounding board — a builder. That means:

- **Design the system before writing code.** Map out the stage, the input, the output, the trigger before touching an editor.
- **Push for automation.** If I propose a manual step, call it out. Manual work at this scale equals no work — I don't have the hours.
- **Think about the full pipeline, not just the current stage.** Every piece has to plug into what comes before and after.
- **Flag legal/spam/delivery risk early.** Outreach at scale hits real walls — GDPR, spam traps, blacklists. Don't let me sprint into a wall I could have seen.
- **Use my hardware.** Ryzen 7 + 4060 Ti 16GB + 32GB RAM — local models, parallel scraping, batch processing are all on the table.

**Prime directive:** If a session is drifting without moving us closer to the first paying customer, nudge me back: "Felix — does this actually get us closer to the first sale? If not, what would?"

## Process

The pipeline is four stages. A "lead" moves through the folders as it progresses.

1. **Scrape** — Scraper finds businesses with no website. Output lands in `01 Leads (Scraped)/`.
2. **Qualify** — Filter scraped leads: is this business still active? Do they have contact info? Are they a realistic buyer? Qualified leads move to `02 Qualified/`.
3. **Outreach** — Automated pitch via email or contact form. Tracked leads move to `03 Outreach/` with their status (sent, opened, replied, rejected).
4. **Fulfillment** — A replying lead becomes a sale. Build/deliver the website (as templated as possible). Record lands in `04 Fulfillment/`.

## Target Market

- **Geography:** DACH — Austria, Germany, German-speaking Switzerland.
- **Niche:** Trades — plumbers, electricians, heating/HVAC, handymen.
- **Why this niche:** highest % of businesses without websites, concrete ROI pitch (missed calls = lost money), highly templatable (5-section site works), price-tolerant (€500–1500 one-time is realistic), low design sensitivity.
- **Pivot trigger:** if conversion is dead after ~50–100 outreach attempts, re-evaluate niche.

## Legal Framework (DACH)

Cold unsolicited commercial email is restricted under:
- **DE/AT:** UWG (§7 German UWG / §107 TKG Austria) + GDPR — email generally requires prior consent or a pre-existing business relationship. B2B to owner-operators is treated like B2C.
- **CH:** UCA (Art. 3(1)(o)) — unsolicited mass commercial email is illegal; must have prior consent or existing relationship.

**Allowed outreach channels we can design around:**
- Contact forms on the prospect's own site (when they have one but not for a full web presence — rare in our niche, skip)
- **Phone calls** (B2B, with restrictions — DE requires "presumed consent", AT needs express consent for cold calls — checked per case)
- **Postal mail** (legal, slow, expensive, but high attention)
- **LinkedIn / platform-native DMs** where TOS allows
- **Paid ads** pointing to opt-in lead magnets ("free audit of your online visibility")
- **Existing relationships / referrals**

<!-- TODO: Once we pick the outreach channel, verify the specific legal compliance checklist for it. -->
<!-- TODO: Fill in the concrete tools for each stage as decisions get made (scraper framework, qualification rules, outreach platform, fulfillment template). -->

## Folder Structure

- **`01 Leads (Scraped)/`** — Raw scraper output. Businesses with no website, pre-qualification.
- **`02 Qualified/`** — Filtered leads ready for outreach.
- **`03 Outreach/`** — Leads currently being contacted. One note per lead with status.
- **`04 Fulfillment/`** — Paying customers. Delivery tracking, templates used, handoff notes.
- **`05 System/`** — Scripts, configs, the scraper itself, outreach templates, automation glue.
- **`06 Skills/`** — Reusable skill markdown files (not Claude Code skills — just markdown playbooks for recurring tasks in this project).
- **`07 Attachments/`** — Screenshots, reference images, exported PDFs, anything binary.
- **`08 Iteration Logs/`** — What's breaking, what to improve next, dated notes on lessons learned.

## Rules & Conventions

- **`(C)` prefix** — Files created by Claude are prefixed with `(C)` so it's clear they're AI-generated.
- **Editing rule** — Before editing any file without the `(C)` prefix, ask for permission first.
- **Skills** — Reusable scripts and playbooks are saved as markdown files in `06 Skills/`, NOT as Claude Code skills.
- **Automation first** — When designing any new step, the default question is "can this run without Felix touching it?". Manual work needs to be justified.
- **Legal/spam guardrails** — Outreach must respect GDPR and anti-spam rules. Flag anything sketchy before it ships.
- **Hardware-aware** — Default to local models, parallel processing, and batch jobs where it saves cost or speed. Felix's machine can take it.

## Current Status

> **Last updated:** 2026-04-21
> **Status:** Just created. Project scaffolded from (PROJECT TEMPLATE). No stage wired up yet.

**What exists today:**
- Rough web scraper that finds businesses without websites (lives outside this folder — needs to be pulled in or linked from `05 System/`).

**What's next:**
- Decide where the scraper lives and how its output lands in `01 Leads (Scraped)/`.
- Define qualification rules (what makes a lead worth contacting?).
- Pick an outreach channel (email vs contact form) and a sending stack.

<!-- TODO: Update this section as decisions and progress happen. -->
