import warnings

import httpx

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

QUERY_TEMPLATE = """
[out:json][timeout:60];
area[name="{region}"]->.searchArea;
(
  nwr["phone"]["name"][!"website"][!"contact:website"][!"url"][!"contact:url"][!"website:en"][!"website:de"][!"website:mobile"](area.searchArea);
);
out body;
"""

WEBSITE_TAGS = {
    "website", "contact:website", "url", "contact:url",
    "website:en", "website:de", "website:mobile",
}


def _parse_tags(element: dict) -> dict:
    tags = element.get("tags", {})
    name = tags.get("name", "Unknown")
    phone = tags.get("phone") or tags.get("contact:phone", "")
    email = tags.get("email") or tags.get("contact:email", "")
    city = tags.get("addr:city", "")
    street = tags.get("addr:street", "")
    housenumber = tags.get("addr:housenumber", "")
    address = " ".join(filter(None, [street, housenumber, city])) or "N/A"
    category = (
        tags.get("shop")
        or tags.get("amenity")
        or tags.get("craft")
        or tags.get("office")
        or "other"
    )
    has_website = any(tags.get(t) for t in WEBSITE_TAGS)
    return {"name": name, "phone": phone, "email": email, "address": address, "category": category, "has_website": has_website}


def search_businesses(region: str) -> list[dict]:
    """Query Overpass for businesses with phone but no website in the given region."""
    query = QUERY_TEMPLATE.format(region=region)
    last_error = None
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
        if not parsed["phone"] or parsed["has_website"]:
            continue
        key = (parsed["name"], parsed["phone"])
        if key in seen:
            continue
        seen.add(key)
        results.append(parsed)
    return results
