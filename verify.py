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
    "wirtschaft.at", "allbiz.at", "firmeninfo.at", "kompass.com",
    "infobel.com", "infobel.at", "tupalo.com", "cybo.com",
    "yellowmap.de", "branchenportal24.de", "werkenntdenbesten.de",
    "9292.at", "firmenbuch.at", "ergebnis.at", "anbieter.at",
    # regional news/portals with business listings — not an own website
    "vol.at", "meinbezirk.at", "vienna.at", "krone.at", "laendleanzeiger.at",
    # OSM/map mirrors — they republish the same OSM data we scraped
    "mapcarta.com", "osm.org", "wheelmap.org", "foursquare.com", "waze.com",
    "bergfex.at", "bergfex.com", "mapy.cz", "maps.me",
    # phone books, job boards, marketplaces
    "dastelefonbuch.de", "telefonabc.at", "wogibtswas.at", "willhaben.at",
    "northdata.de", "firmenwissen.de", "kununu.com", "indeed.com",
    "stepstone.at", "hotfrog.de", "hotfrog.at", "alleskralle.com",
    "oeffnungszeitenbuch.de", "finde-offen.at", "geoportal.at",
    "fimag.at", "bauwohnwelt.at", "wo-in-vorarlberg.at", "firmania.at",
    "daibau.at",
    # gastro/beauty/booking platforms (niche widened 2026-06-10) —
    # a Lieferando/Treatwell/Booking profile is NOT an own website
    "lieferando.at", "lieferando.de", "mjam.at", "foodora.at",
    "speisekarte.de", "speisekarte.menu", "falstaff.com", "falstaff.at",
    "restaurantguru.com", "thefork.com", "thefork.at", "quandoo.at",
    "quandoo.de", "happycow.net", "treatwell.at", "treatwell.de",
    "planity.com", "salonkee.at", "booking.com", "airbnb.com", "airbnb.at",
    "hotels.com", "expedia.com", "holidaycheck.de", "holidaycheck.at",
}

# A directory entry on an unknown domain betrays itself in the URL path:
# /firmen/, /auskunft/, /branchen/… — an own website's hit is the homepage.
DIRECTORY_PATH_HINTS = re.compile(
    r"/(firmen|firma|auskunft|branchen|brancheneintrag|eintrag|verzeichnis|"
    r"unternehmen|betriebe|gewerbe|company|companies|listing|profil)e?[-_/]",
    re.IGNORECASE)

SKIP_DOMAINS = {"google", "brave", "bing", "yahoo", "duckduckgo"}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_DDG_URL = "https://html.duckduckgo.com/html/"


_GENERIC_TOKENS = {"gmbh", "und", "kg", "og"}


def _name_tokens(name: str) -> list[str]:
    """Business-name tokens usable as domain evidence (umlauts folded)."""
    folded = (name.lower().replace("ä", "ae").replace("ö", "oe")
              .replace("ü", "ue").replace("ß", "ss"))
    return [t for t in re.findall(r"[a-z]+", folded)
            if len(t) >= 4 and t not in _GENERIC_TOKENS]


def _first_own_domain(urls: list[str], name: str = "") -> str | None:
    """First URL that plausibly IS the business's own website.

    Blocklists never keep up with directory/aggregator sites, so unknown
    domains must earn trust: either a business-name token appears in the
    domain, or the hit is the domain's homepage. Directory hits are deep
    links on unrelated domains and fail both tests. False rejects only
    leave the lead 'clean', where Felix's review catches it — false
    accepts would silently throw the lead away.
    """
    tokens = _name_tokens(name)
    for url in urls:
        m = re.match(r"https?://(?:www\.)?([^/]+)(/?[^?#]*)", url)
        if not m:
            continue
        domain, path = m.group(1).lower(), m.group(2)
        if any(d in domain for d in DIRECTORY_DOMAINS):
            continue
        if any(s in domain for s in SKIP_DOMAINS):
            continue
        if DIRECTORY_PATH_HINTS.search(url):
            continue
        token_match = any(t in domain for t in tokens)
        is_homepage = path in ("", "/")
        if token_match or is_homepage:
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
    found_url = _first_own_domain([r.get("url", "") for r in results], name)
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
    found_url = _first_own_domain(raw_urls, name)
    return {"has_website": bool(found_url), "url": found_url,
            "exists": exists, "error": None}
