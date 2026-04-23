import warnings

import httpx

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Broad query: any business with phone but no website (original behaviour).
QUERY_TEMPLATE = """
[out:json][timeout:60];
area[name="{region}"]->.searchArea;
(
  nwr["phone"]["name"][!"website"][!"contact:website"][!"url"][!"contact:url"][!"website:en"][!"website:de"][!"website:mobile"](area.searchArea);
);
out body;
"""

# OSM craft tags we consider "trades" (DACH Handwerker) for the Automatic Webside Seller pipeline.
# Source: OpenStreetMap Wiki — Key:craft. See https://wiki.openstreetmap.org/wiki/Key:craft
TRADES_CRAFT_TAGS = [
    "electrician",
    "plumber",
    "hvac",
    "heating_engineer",
    "carpenter",
    "painter",
    "roofer",
    "tiler",
    "glazier",
    "locksmith",
    "metal_construction",
    "gasfitter",
    "stonemason",
    "plasterer",
    "floorer",
    "handyman",
]

# Trades-only query: filter at Overpass level by craft tag. Smaller payload, cleaner data.
TRADES_QUERY_TEMPLATE = """
[out:json][timeout:60];
area[name="{region}"]->.searchArea;
(
  nwr["craft"~"^({craft_regex})$"]["name"][!"website"][!"contact:website"][!"url"][!"contact:url"][!"website:en"][!"website:de"][!"website:mobile"](area.searchArea);
);
out body;
"""

WEBSITE_TAGS = {
    "website", "contact:website", "url", "contact:url",
    "website:en", "website:de", "website:mobile",
}


def _build_query(region: str, niche: str | None = None) -> str:
    """Build an Overpass QL query for a region. If niche='trades', filter to trades craft tags."""
    if niche == "trades":
        craft_regex = "|".join(TRADES_CRAFT_TAGS)
        return TRADES_QUERY_TEMPLATE.format(region=region, craft_regex=craft_regex)
    return QUERY_TEMPLATE.format(region=region)


def _parse_tags(element: dict) -> dict:
    tags = element.get("tags", {})
    name = tags.get("name", "Unknown")
    phone = tags.get("phone") or tags.get("contact:phone", "")
    email = tags.get("email") or tags.get("contact:email", "")
    city = tags.get("addr:city", "")
    street = tags.get("addr:street", "")
    housenumber = tags.get("addr:housenumber", "")
    postcode = (
        tags.get("addr:postcode")
        or tags.get("addr:postalcode")
        or tags.get("contact:postalcode", "")
    )
    address = " ".join(filter(None, [street, housenumber, city])) or "N/A"
    category = (
        tags.get("craft")
        or tags.get("shop")
        or tags.get("amenity")
        or tags.get("office")
        or "other"
    )
    has_website = any(tags.get(t) for t in WEBSITE_TAGS)
    return {
        "name": name,
        "phone": phone,
        "email": email,
        "address": address,
        "postcode": postcode,
        "category": category,
        "has_website": has_website,
    }


def search_businesses(region: str, niche: str | None = None) -> list[dict]:
    """Query Overpass for businesses with no website in the given region.

    niche=None     → broad search: any business with phone, no website (original behaviour).
    niche='trades' → trades-only: craft tag must be in TRADES_CRAFT_TAGS. Phone optional
                     (postal mail is primary channel, so we don't drop leads lacking phone).
    """
    query = _build_query(region, niche)
    last_error = None
    resp = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                resp = httpx.post(
                    endpoint,
                    data={"data": query},
                    timeout=90,
                    verify=False,
                )
            resp.raise_for_status()
            break
        except httpx.HTTPError as e:
            print(f"[scraper] {endpoint} failed: {e}, trying next...")
            last_error = e
    else:
        raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_error}")

    elements = resp.json().get("elements", [])
    results = []
    seen = set()
    for el in elements:
        parsed = _parse_tags(el)
        # For broad search, require phone and drop anything that slipped through with a website.
        # For trades, phone is optional — postal mail is the primary channel.
        if parsed["has_website"]:
            continue
        if niche != "trades" and not parsed["phone"]:
            continue
        key = (parsed["name"], parsed["phone"], parsed["address"])
        if key in seen:
            continue
        seen.add(key)
        results.append(parsed)
    return results
