"""verify-local.py — qualify leads from Felix's residential IP.

Why local: DuckDuckGo (and Google) challenge datacenter IPs almost
immediately, but tolerate a residential IP at a polite pace. So this script
runs on Felix's PC (like generate-letters.py), checks each lead via DDG with
15-20s spacing, and PATCHes the verdict back to the Railway API.

If BRAVE_API_KEY is set locally, Brave is used instead (1.1s spacing).

Usage:
    $env:AUTH_PASS = "<railway admin pass>"
    python verify-local.py                # verify all status=New leads
    python verify-local.py --limit 10     # first 10 only
    python verify-local.py --status New --dry-run   # check, don't write

Outcomes per lead:
    has_website  → PATCH status="Has Website" + website_url
    phantom      → PATCH status="Phantom" + note
    clean        → no PATCH (stays eligible for outreach)
    error        → no PATCH (prints reason; challenge pages trigger backoff)

Railway 5xx / network errors are retried with backoff (5/15/45s). If a PATCH
still fails, the lead stays status=New and is re-checked on the next run.
Three consecutive PATCH failures abort the run — Railway is down, no point
burning search queries whose verdicts can't be saved.
"""

import argparse
import os
import random
import sys
import time

import httpx

from qualify import REALISTIC_CATEGORIES, hard_disqualify, repair_postcode, score
from scraper import TRADES_CRAFT_TAGS
from verify import check_website_brave, check_website_ddg

BASE = os.environ.get("BUSINESS_FINDER_URL", "https://handwerkerweb.at")
AUTH_USER = os.environ.get("AUTH_USER", "admin")
AUTH_PASS = os.environ.get("AUTH_PASS", "")
BRAVE_KEY = os.environ.get("BRAVE_API_KEY", "")

DDG_DELAY = (15, 20)      # polite residential pacing, randomized
BRAVE_DELAY = (1.1, 1.5)
CHALLENGE_BACKOFF = 90    # seconds to wait after a DDG challenge page
MAX_CONSECUTIVE_CHALLENGES = 2

RETRY_SLEEPS = (5, 15, 45)        # Railway 502s usually clear within a minute
MAX_CONSECUTIVE_PATCH_FAILS = 3   # then Railway is down — stop the run
RAILWAY_ABORT = ("\nABORT: Railway PATCHes keep failing — backend looks down. "
                 "Unsaved leads stay status=New and are re-checked next run.")


def railway_call(do_request, desc: str):
    """One Railway request, retrying 5xx/network errors with backoff.

    4xx raises immediately (auth/data bug — a retry can't fix it).
    Returns the response, or None once all retries are exhausted."""
    for pause in (*RETRY_SLEEPS, None):
        try:
            resp = do_request()
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp
            err = f"HTTP {resp.status_code}"
        except httpx.TransportError as exc:
            err = type(exc).__name__
        if pause is None:
            print(f"    {desc}: {err} — giving up")
            return None
        print(f"    {desc}: {err} — retrying in {pause}s")
        time.sleep(pause)


def check(name: str, region: str) -> dict:
    if BRAVE_KEY:
        return {**check_website_brave(name, region, BRAVE_KEY), "engine": "brave"}
    return {**check_website_ddg(name, region), "engine": "ddg"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", default="New")
    ap.add_argument("--region", default=None,
                    help="e.g. Vorarlberg — strongly recommended")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--trades", action="store_true",
                    help="only trades categories (the original niche)")
    ap.add_argument("--realistic", action="store_true",
                    help="all owner-run local categories (niche v2, 2026-06-10)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not AUTH_PASS:
        print("ERROR: set $env:AUTH_PASS first (Railway admin password).")
        return 1

    client = httpx.Client(base_url=BASE, auth=(AUTH_USER, AUTH_PASS), timeout=30)
    # fetch everything first — --limit caps AFTER category filtering,
    # otherwise the first N rows may contain zero relevant categories
    params = {"status": args.status, "limit": 500}
    if args.region:
        params["region"] = args.region
    resp = railway_call(
        lambda: client.get("/businesses", params=params), "GET /businesses")
    if resp is None:
        print("ABORT: Railway unreachable — try again later.")
        return 1
    rows = resp.json()
    if isinstance(rows, dict):
        rows = rows.get("items", rows.get("rows", []))
    if args.trades:
        rows = [r for r in rows if r.get("category") in TRADES_CRAFT_TAGS]
    if args.realistic:
        rows = [r for r in rows if r.get("category") in REALISTIC_CATEGORIES]
    rows = rows[:args.limit]
    print(f"{len(rows)} lead(s) with status={args.status!r} "
          f"— engine: {'brave' if BRAVE_KEY else 'ddg'}"
          f"{' (DRY RUN)' if args.dry_run else ''}\n")

    counts = {"disqualified": 0, "has_website": 0, "phantom": 0,
              "clean": 0, "error": 0}
    challenges = 0
    patch_fails = 0
    lo, hi = BRAVE_DELAY if BRAVE_KEY else DDG_DELAY

    def save(biz_id, payload) -> bool:
        """PATCH one verdict. False = run must abort (Railway down)."""
        nonlocal patch_fails
        if railway_call(lambda: client.patch(f"/businesses/{biz_id}",
                                             json=payload),
                        f"PATCH {biz_id}") is None:
            counts["error"] += 1
            patch_fails += 1
            return patch_fails < MAX_CONSECUTIVE_PATCH_FAILS
        patch_fails = 0
        return True

    for i, biz in enumerate(rows, 1):
        name, region = biz["name"], biz.get("region", "")

        # Stage 1 — hard disqualifiers, no search query wasted on junk
        reason = hard_disqualify(biz)
        if reason:
            counts["disqualified"] += 1
            print(f"  [{i}/{len(rows)}] {name}: AUTO-REJECT — {reason}")
            if not args.dry_run and not save(biz["id"], {
                    "status": "Rejected", "notes": f"Auto: {reason}"}):
                print(RAILWAY_ABORT)
                return 2
            continue

        # Stage 2 — repair missing PLZ from the town name
        new_plz = repair_postcode(biz)
        if new_plz:
            biz["postal_code"] = new_plz
            # ASCII arrow: redirected output on Windows is cp1252, U+2192 crashes
            print(f"  [{i}/{len(rows)}] {name}: PLZ ergänzt -> {new_plz}")

        result = check(name, region)

        if result.get("error"):
            if "challenge" in result["error"]:
                challenges += 1
                if challenges >= MAX_CONSECUTIVE_CHALLENGES:
                    print(f"\nABORT: {challenges} challenge pages in a row — "
                          f"IP is flagged. Re-run in an hour.")
                    return 2
                print(f"  [{i}/{len(rows)}] {name}: challenge page — "
                      f"backing off {CHALLENGE_BACKOFF}s")
                time.sleep(CHALLENGE_BACKOFF)
            else:
                print(f"  [{i}/{len(rows)}] {name}: ERROR {result['error']}")
            counts["error"] += 1
            continue
        challenges = 0

        if result["has_website"]:
            counts["has_website"] += 1
            verdict, patch = f"HAS WEBSITE  {result['url']}", {
                "status": "Has Website", "website_url": result["url"]}
        elif result["exists"] is False:
            counts["phantom"] += 1
            verdict, patch = "PHANTOM (zero search results)", {
                "status": "Phantom",
                "notes": "Auto: zero search results — likely OSM phantom "
                         "(verify-local)"}
        else:
            # Stage 3 — clean lead: score it so review shows best first
            counts["clean"] += 1
            pts = score(biz, exists=result["exists"])
            verdict, patch = f"CLEAN — Score P{pts}", {"priority": pts}

        if new_plz and patch is not None:
            patch["postal_code"] = new_plz

        print(f"  [{i}/{len(rows)}] {name}: {verdict}")
        if patch and not args.dry_run and not save(biz["id"], patch):
            print(RAILWAY_ABORT)
            return 2

        if i < len(rows):
            time.sleep(random.uniform(lo, hi))

    print(f"\nDone. disqualified={counts['disqualified']}  "
          f"has_website={counts['has_website']}  phantom={counts['phantom']}  "
          f"clean={counts['clean']}  errors={counts['error']}")
    print("Clean leads keep status=New with a P1-P10 score (priority). "
          "Review shows highest score first — spot-check ~3 before letters!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
