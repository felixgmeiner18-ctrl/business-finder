import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

QUERY_TEMPLATE = """
[out:json][timeout:60];
area[name="{region}"]->.searchArea;
(
  nwr["phone"]["name"](if: !is_tag("website"))(area.searchArea);
);
out body;
"""


def _parse_tags(element: dict) -> dict:
    tags = element.get("tags", {})
    name = tags.get("name", "Unknown")
    phone = tags.get("phone") or tags.get("contact:phone", "")
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
    return {"name": name, "phone": phone, "address": address, "category": category}


def search_businesses(region: str) -> list[dict]:
    """Query Overpass for businesses with phone but no website in the given region."""
    query = QUERY_TEMPLATE.format(region=region)
    try:
        resp = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=90,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Overpass API error: {e}") from e

    elements = resp.json().get("elements", [])
    results = []
    seen = set()
    for el in elements:
        parsed = _parse_tags(el)
        if not parsed["phone"]:
            continue
        key = (parsed["name"], parsed["phone"])
        if key in seen:
            continue
        seen.add(key)
        results.append(parsed)
    return results
