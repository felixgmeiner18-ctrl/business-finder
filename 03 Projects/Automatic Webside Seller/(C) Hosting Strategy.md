# Hosting Strategy — Product Decision

> **Status:** Open — decision needed before first paying customer.
> **Trigger:** 2026-04-24 — removed "Hosting und Domain im ersten Jahr inklusive" from Letter v1. Now need to decide what hosting actually is in our product.

## The decision in one sentence

Do we sell a one-time build (€590, customer handles hosting later), or do we also sell a monthly hosting + maintenance fee on top?

## Why this came up

In v1 of the letter the offer was:

> "Festpreis 590 Euro für den Standardumfang — einmalig, alles inklusive. Hosting und Domain im ersten Jahr inklusive."

Felix flagged three problems with that line:

1. **Operational:** "What does 'inklusive' actually mean after year 1?" — we never defined it.
2. **Legal:** "If the customer doesn't pay, can I just turn off their website?" — not obviously yes.
3. **Strategic:** Recurring hosting could be a monthly revenue stream we shouldn't give away for free.

So we stripped the line from the letter and parked this doc to decide properly.

## How to host many small-business sites cleanly

A Vorarlberg trades website is static or near-static: header, 4-6 pages, contact form, some photos. ~5 MB of assets. Almost zero traffic (say 50 visits/month for a small Tischlerei). This is the easiest hosting workload that exists.

**Recommended platform: Cloudflare Pages.**

| | Cloudflare Pages | Netlify | Railway | VPS + Caddy |
|---|---|---|---|---|
| Cost for 10 sites | €0 | €0 | ~€50/mo | ~€5/mo |
| Max sites on free tier | 500 | 500 | n/a | unlimited |
| Custom domain | Free | Free | Free | Free |
| SSL cert | Auto | Auto | Auto | Auto (via Caddy) |
| Unified dashboard | ✅ | ✅ | ✅ | Built yourself |
| Git auto-deploy | ✅ | ✅ | ✅ | Yes (with hooks) |
| Analytics built-in | ✅ | Partial | ❌ | Built yourself |
| Forms endpoint | Workers (free) | Paid | Yours | Yours |
| DDoS protection | ✅ | ✅ | Partial | Yours |

**Pick: Cloudflare Pages.** 500 sites free forever, same account, one dashboard. Up to ~€5,000/year of customer revenue before hosting even shows up as a cost line. Route-by-subdomain (e.g. `tischlerei-braendle.at`) is a free DNS setup on Cloudflare. Forms submit to a single Cloudflare Worker that emails the customer — also free.

**Revisit only when** we cross 500 sites (good problem to have) or need server-side rendering (not in scope for trades sites).

## Business model — three options

### Model A: One-time only

- Customer pays €590.
- We register their domain in **their name and on their billing** (key legal point — see below).
- We host on Cloudflare Pages, pointing at their domain.
- After year 1, customer keeps their domain (they renew directly with the registrar, ~€10-15/yr) and can move hosting anywhere. We hand over the source code if asked.
- **Revenue:** €590 × number of customers. That's it.

**Pros:** zero ongoing obligation, no non-payment drama, easy to scale because there's no support load.
**Cons:** no recurring revenue. When the scraper runs out of leads, income stops.

### Model B: One-time + optional monthly

- €590 for the build (as Model A).
- **Optional** monthly package: €12/mo or €120/yr, auto-renew.
  - Includes: ongoing hosting, minor text/photo updates (say up to 4 small changes/year), SSL/domain renewal handling, one basic analytics report/quarter.
- Customer can decline at signing — we still register domain in their name and hand over.
- Customer can cancel anytime (standard AT B2B notice: 14 or 30 days).

**Pros:** recurring revenue for ~50% of customers (realistic opt-in rate), still easy to refuse for price-sensitive customers. Margin per site: ~€100-130/yr after domain cost.
**Cons:** support load for minor updates (bounded by the 4-updates/year limit in the contract). Invoicing and payment chasing.

### Model C: One-time + mandatory monthly

- €590 + €12/mo, forced bundle.
- Cheaper list price if Felix prefers: €390 + €12/mo (lower entry barrier).

**Pros:** predictable recurring revenue, simpler pricing pitch, forces the serious customers.
**Cons:** some customers will bounce on the commitment, complicates the initial sale, harder to sell to very small Handwerker who just want a site.

## Pricing math

Assumptions:
- Cloudflare Pages + Workers: €0 hosting cost
- Domain (.at): ~€12/yr at netim/namecheap/Hetzner
- Felix's time for monthly maintenance: probably 15 min / quarter for a quiet customer

Per-site recurring cost: ~€12/yr domain. Everything else is Felix's time.

If we charge €12/mo (€144/yr):
- Gross: €144
- Cost: €12 (domain)
- Gross margin: €132/yr per customer
- At 20 customers on recurring: €2,640/yr passive. At 100: €13,200/yr.

That's a meaningful chunk of the €5,000/mo target — recurring is worth building in, but only if the support load stays low.

## Legal: non-payment and "just turning off the website"

**Short answer:** yes, with a proper contract you can suspend (not delete) a non-paying customer's site. No, you can't do it as a surprise.

**What's required in the contract (AGB):**

1. Clear payment terms (due date, payment method).
2. A **Mahnung escalation clause:** e.g., "Bei Zahlungsverzug folgt eine erste Mahnung nach 14 Tagen, eine zweite nach weiteren 14 Tagen mit Ankündigung der Leistungsaussetzung."
3. A **suspension clause:** "Wird nach der zweiten Mahnung nicht gezahlt, ist der Dienstleister berechtigt, die Webseite vom Netz zu nehmen und bis zum Zahlungseingang ausgesetzt zu halten."
4. A **data retention clause:** "Kundendaten werden trotz Aussetzung mindestens 90 Tage aufbewahrt; eine endgültige Löschung erfolgt erst nach schriftlicher Kundenanweisung oder Vertragsende."

**What you CAN do** after proper notice:

- Take the site offline (Cloudflare Pages — one click to unpublish).
- Pause the domain's DNS (site becomes unreachable but preserved).

**What you CANNOT do:**

- Delete the customer's data without their consent.
- Hold the domain hostage if it's in the customer's name (which is why we register it in their name — see below).
- Remove an unpaid site mid-contract without first exhausting the Mahnung process.
- Use "website shutdown" as a threat without the contract clause being explicit.

**Domain ownership — critical:** register the domain in the **customer's name**, with **their billing email**, paid via our reseller (e.g. Hetzner via their reseller portal). We handle the technical setup; they own the identity. This protects them (and us: we can't be accused of domain hostage).

If customer doesn't pay and we suspend: their domain keeps working (they paid for it or we did on their behalf and rolled it into year 1); only our hosting pointer is cut.

**Legal disclaimer:** This document is a strategy memo, not legal advice. Before first paying customer:

- Register as **Kleinunternehmer (AT)** so contracts have a real legal entity behind them.
- Commission a basic AGB draft from an AT-based lawyer (~€300-500 one-off). There are reasonable boilerplate AGBs for "Webdesign-Dienstleistungen" that can be adapted.
- Have the lawyer verify the suspension clause is enforceable and doesn't accidentally create consumer-protection issues (B2B relaxes most of this, but small one-person Handwerker can sometimes be treated as "Verbraucher" under AT/EU law in some edge cases).

## Current lean

Model B (one-time + optional monthly). Reasoning:

- Keeps €590 entry price intact for price-sensitive customers.
- Most trades businesses will opt in to maintenance once they have a site (they don't want to learn a CMS).
- Builds recurring revenue without forcing it.
- No damage to Phase 1 (8 letters) — the letter is now model-agnostic, we sell the build and mention optional maintenance at the sales conversation, not in the letter.

**Not decided, not committed.** This is Claude's recommendation, not Felix's call yet.

## Decisions needed before first paying customer

- [ ] Pick Model A / B / C (or a variant).
- [ ] Set final pricing on monthly package if we go B or C.
- [ ] Register as Kleinunternehmer (AT).
- [ ] Commission AGB + payment/suspension clauses from an AT lawyer.
- [ ] Cloudflare account + Workers setup for forms endpoint.
- [ ] Domain-registration workflow defined (reseller, who pays, what goes in the customer's name).
- [ ] Template service contract to sign with each customer.

**None of these blocks the Phase 1 letter send.** Phase 1 is "does this pitch get any replies at all." The contract/hosting decisions only need to be locked before we sign the *first* customer — which is weeks away at the earliest.

## What I'm less sure about

- **Opt-in rate for monthly hosting** — my 50% estimate is a guess. Could be 20%, could be 80%. First 5 customers will tell us.
- **Whether to offer Model B pricing at €12 or €15/mo** — depends on how comfortable we are charging Handwerker recurring fees. €12/mo feels right for Phase 1; can raise later for new customers without touching existing ones.
- **Whether "maintenance" should include anything more than text edits** — e.g., "a new photo section once a year." Keep it tight in the contract so the support load is bounded.
