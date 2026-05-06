# DNS Setup — handwerkerweb.at

> **Locked 2026-05-05.** End-to-end live: Cloudflare → Railway → FastAPI lander.

## Architecture

```
Visitor browser
      │
      │  https://handwerkerweb.at/VB02
      ▼
Cloudflare DNS (clyde.ns.cloudflare.com / meadow.ns.cloudflare.com)
      │  CNAME flattening on apex
      ▼
Railway edge (zm29vd8c.up.railway.app)
      │  routes / by domain → service business-finder
      ▼
FastAPI (main.py)
      │  GET /{code}  →  static/lander.html  (only matches ^VB\d{2}$)
      │  POST /api/contact  →  contact_submissions table
      ▼
SQLite DB on Railway volume
```

## Why Cloudflare in the middle

`world4you` (the registrar) **does not allow CNAME records on the apex** (`@` / `handwerkerweb.at` itself). Their DNS UI rejects it with: _"Der Name des CNAME-Records muss eine Subdomain sein."_

Railway only provides a CNAME target — they don't expose a stable apex IP. So we needed something between world4you and Railway that supports apex CNAME flattening. Cloudflare does this for free, no code changes.

## What's configured

### At world4you (registrar)

- Nameservers (Domains → Nameserver):
  - `clyde.ns.cloudflare.com`
  - `meadow.ns.cloudflare.com`

(All other DNS settings — A/MX/SPF — moved to Cloudflare and are managed there now.)

### At Cloudflare (DNS host)

- Site: `handwerkerweb.at` on Free plan.
- DNS records:
  | Type | Name | Content | Proxy |
  |---|---|---|---|
  | CNAME | `@` (apex) | `zm29vd8c.up.railway.app` | DNS only (grey) |
  | CNAME | `www` | `zm29vd8c.up.railway.app` | DNS only (grey) |
  | TXT | `_railway-verify` | `railway-verify=6dc96b5616f300cc48de9d82642fafa93a879fe6dd585c9b2bea3854ed9899fd` | — |

Proxy is **OFF** (grey cloud) on the CNAMEs — Railway needs DNS-only resolution to verify ownership and terminate SSL itself. We can revisit this later (turn on Cloudflare proxy + SSL/TLS "Full strict") if we want CDN/DDoS in front of Railway, but for Phase 1 it's not needed.

Records inherited from world4you that were deleted at Cloudflare: `ftp` A, `mail` A, `MX handwerkerweb.at`. Felix doesn't need email or FTP on this domain — outreach uses Gmail.

### At Railway (origin)

- Service `business-finder`, environment `production`
- Custom domains added under Settings → Public Networking:
  - `handwerkerweb.at` → Port 8080 (Python)
- Domain status: **Active** (verified via the `_railway-verify` TXT and the apex CNAME)

## Smoke tests (verified 2026-05-05)

```
$ host handwerkerweb.at
handwerkerweb.at has address 66.33.22.4

$ curl -sI https://handwerkerweb.at/VB02 | head -3
HTTP/2 200
content-type: text/html
server: railway-edge

$ curl -s -X POST https://handwerkerweb.at/api/contact \
    -H "Content-Type: application/json" \
    -d '{"name":"DNS Test","email":"","phone":"+436641234567","message":"[Tracking: VB02]\nFirma: DNS Live Test"}'
{"ok":true}
```

Submission visible in `GET /api/contact/list` (admin-protected).

## Cost

- Cloudflare Free plan: €0/yr.
- world4you domain: €12 first year, €36/yr from year 2 (transferable to a cheaper registrar before renewal — Cloudflare Registrar costs ~€10/yr at-cost, but doesn't sell `.at`).
- Railway: existing usage, no extra cost for adding a custom domain.

**Recurring cost for Phase 1: €0/month** (Railway is on whatever plan Felix already pays).

## What can break and how to debug

| Symptom | Likely cause | Fix |
|---|---|---|
| `nslookup handwerkerweb.at` returns world4you IP (`81.19.154.x`) | Nameserver propagation not done | Wait 1–24h. Most regions update in 5–30 min. |
| `nslookup` resolves but `https://` returns SSL error | Railway hasn't issued cert yet | Wait 5–10 min after DNS resolves. Railway auto-issues Let's Encrypt. |
| `https://` works but `/VB02` returns 404 | Railway redeploy needed OR route regex broken | Check Railway Deployments tab; verify latest commit deployed. |
| Form submit succeeds (200) but no row appears | DB write failed silently | Check Railway logs for the POST /api/contact; should see `200` with no error. |
| `nslookup` resolves to Cloudflare IP | Proxy is ON (orange cloud) | Toggle proxy OFF on the CNAME records in Cloudflare DNS panel. Railway custom-domain SSL won't validate behind Cloudflare proxy unless we configure SSL/TLS "Full strict". |

## Rollback

If we ever need to undo this:
1. At world4you: Nameserver → "Standard Nameserver eintragen" (restores `ns1.world4you.at` / `ns2.world4you.at`).
2. At Railway: remove `handwerkerweb.at` from custom domains.
3. Cloudflare account stays — costs nothing idle.

## Next time we touch this

When Phase 1 ends and we expand to Germany / Switzerland, we may want:
- A **www.handwerkerweb.at** redirect to apex (currently both work, slightly redundant).
- Cloudflare proxy ON with SSL/TLS Full strict for DDoS protection at scale.
- A second domain (`handwerkerweb.de` for German leads) added as a second site at Cloudflare — same Railway origin.

For now, none of that matters. Phase 1 mails 8 letters. We measure response rate. We iterate.
