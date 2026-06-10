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
"""

import argparse
import os
import random
import sys
import time

import httpx

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
                    help="only trades categories (the locked niche)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not AUTH_PASS:
        print("ERROR: set $env:AUTH_PASS first (Railway admin password).")
        return 1

    client = httpx.Client(base_url=BASE, auth=(AUTH_USER, AUTH_PASS), timeout=30)
    params = {"status": args.status, "limit": args.limit}
    if args.region:
        params["region"] = args.region
    rows = client.get("/businesses", params=params).raise_for_status().json()
    if isinstance(rows, dict):
        rows = rows.get("items", rows.get("rows", []))
    if args.trades:
        rows = [r for r in rows if r.get("category") in TRADES_CRAFT_TAGS]
    print(f"{len(rows)} lead(s) with status={args.status!r} "
          f"— engine: {'brave' if BRAVE_KEY else 'ddg'}"
          f"{' (DRY RUN)' if args.dry_run else ''}\n")

    counts = {"has_website": 0, "phantom": 0, "clean": 0, "error": 0}
    challenges = 0
    lo, hi = BRAVE_DELAY if BRAVE_KEY else DDG_DELAY

    for i, biz in enumerate(rows, 1):
        name, region = biz["name"], biz.get("region", "")
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
            counts["clean"] += 1
            verdict, patch = "clean — no website, business exists", None

        print(f"  [{i}/{len(rows)}] {name}: {verdict}")
        if patch and not args.dry_run:
            client.patch(f"/businesses/{biz['id']}", json=patch).raise_for_status()

        if i < len(rows):
            time.sleep(random.uniform(lo, hi))

    print(f"\nDone. has_website={counts['has_website']}  "
          f"phantom={counts['phantom']}  clean={counts['clean']}  "
          f"errors={counts['error']}")
    print("Clean leads keep status and are the outreach pool. "
          "Spot-check ~3 of them manually before generating letters!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
