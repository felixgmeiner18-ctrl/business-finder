"""Website / existence verification for scraped leads.

Two engines, same contract — both return:
    {"has_website": bool, "url": str|None, "exists": bool|None, "error": str|None}

exists=False  → zero search results mention the business → likely OSM phantom
exists=None   → engine failed / can't tell. Caller must NOT mark the row.

Engines:
  check_website_brave — Brave Search API. Reliable from datacenter IPs,
      needs BRAVE_API_KEY (free $5/month credit ≈ 1,000 queries).
  check_website_ddg   — DuckDuckGo HTML scrape. No key, but DDG serves an
      "anomaly" challenge page after a handful of rapid requests, especially
      from datacenter IPs. Use from a residential IP with 15s+ delays
      (see verify-local.py). Fails loudly instead of guessing.
"""

import html as html_lib
import re
import urllib.parse

import httpx

DIRECTORY_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "yelp.com", "tripadvisor.com", "tripadvisor.de",
    "google.com", "google.de", "maps.google.com",
    "gelbeseiten.de", "dasoertliche.de", "meinestadt.de",
    "11880.com", "branchenbuch.de", "golocal.de",
    "youtube.com", "tiktok.com", "pinterest.com",
    "openstreetmap.org", "wikipedia.org",
    # Austrian directories — a listing there is NOT an own website
    "herold.at", "firmenabc.at", "wko.at", "cylex.at", "cylex.de",
    "stadtbranchenbuch.at", "oeffnungszeiten.at", "firmen.at",
}

SKIP_DOMAINS = {"google", "brave", "bing", "yahoo", "duckduckgo"}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_DDG_URL = "https://html.duckduckgo.com/html/"


def _first_own_domain(urls: list[str]) -> str | None:
    """First URL whose domain is neither a directory nor a search engine."""
    for url in urls:
        m = re.match(r"https?://(?:www\.)?([^/]+)", url)
        if not m:
            continue
        domain = m.group(1).lower()
        if any(d in domain for d in DIRECTORY_DOMAINS):
            continue
        if any(s in domain for s in SKIP_DOMAINS):
            continue
        return url
    return None


def check_website_brave(name: str, region: str, api_key: str) -> dict:
    """Brave Search API check. Free tier: 1 req/s."""
    query = f'"{name}" {region}'
    try:
        resp = httpx.get(
            _BRAVE_SEARCH_URL,
            params={"q": query, "count": 5, "country": "AT", "search_lang": "de"},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        return {"has_website": False, "url": None, "exists": None, "error": str(e)}

    results = resp.json().get("web", {}).get("results", [])
    if not results:
        return {"has_website": False, "url": None, "exists": False, "error": None}

    name_lower = name.lower()
    exists = any(
        name_lower in r.get("title", "").lower()
        or name_lower in r.get("description", "").lower()
        for r in results
    )
    found_url = _first_own_domain([r.get("url", "") for r in results])
    return {"has_website": bool(found_url), "url": found_url,
            "exists": exists, "error": None}


def check_website_ddg(name: str, region: str) -> dict:
    """DuckDuckGo HTML check. No key; throttle to ≥15s between calls and
    expect challenge pages under load — those come back as error, never
    as a (false) verdict."""
    query = f"{name} {region}"  # unquoted: exact-phrase quoting kills recall
    try:
        resp = httpx.get(
            _DDG_URL,
            params={"q": query, "kl": "at-de"},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        return {"has_website": False, "url": None, "exists": None, "error": str(e)}

    page = resp.text
    low = page.lower()
    if "anomaly" in low or "challenge" in low or "captcha" in low:
        return {"has_website": False, "url": None, "exists": None,
                "error": "ddg: challenge page (rate-limited) — back off"}

    # DDG result links are redirects: /l/?uddg=<urlencoded-target>&rut=…
    raw_urls = [urllib.parse.unquote(u) for u in re.findall(r'uddg=([^&"]+)', page)]

    if not raw_urls:
        if 'class="result' in page or "no-results" in low:
            return {"has_website": False, "url": None,
                    "exists": False, "error": None}
        return {"has_website": False, "url": None, "exists": None,
                "error": "ddg: unexpected page (markup changed?)"}

    # Existence: name appears in titles/snippets. Unescape first —
    # "Hase & Kramer" arrives as "Hase &amp; Kramer" in raw HTML.
    exists = name.lower() in html_lib.unescape(page).lower()
    found_url = _first_own_domain(raw_urls)
    return {"has_website": bool(found_url), "url": found_url,
            "exists": exists, "error": None}
