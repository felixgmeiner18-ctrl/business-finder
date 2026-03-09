import os
import re
import secrets
import threading
import warnings
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import (
    delete_business,
    get_business,
    get_businesses,
    init_db,
    update_business,
    upsert_business,
)
from scraper import search_businesses


class UpdatePayload(BaseModel):
    status: str | None = None
    notes: str | None = None
    follow_up: str | None = None


class SearchPayload(BaseModel):
    region: str


class QueuePayload(BaseModel):
    regions: list[str]


_search_state = {"searching": False, "region": "", "queue": [], "queue_total": 0, "queue_done": 0}

# Domains that are NOT a real business website (directories, social, maps)
DIRECTORY_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "yelp.com", "tripadvisor.com", "tripadvisor.de",
    "google.com", "google.de", "maps.google.com",
    "gelbeseiten.de", "dasoertliche.de", "meinestadt.de",
    "11880.com", "branchenbuch.de", "golocal.de",
    "youtube.com", "tiktok.com", "pinterest.com",
    "openstreetmap.org", "wikipedia.org",
}


def run_search(region: str):
    _search_state["searching"] = True
    _search_state["region"] = region
    try:
        businesses = search_businesses(region)
        count = 0
        for b in businesses:
            if upsert_business(b["name"], b["phone"], b["address"], b["category"], region, b.get("email", "")):
                count += 1
        print(f"[search] {region}: {len(businesses)} found, {count} new")
    except RuntimeError as e:
        print(f"[search] error: {e}")
    finally:
        _search_state["searching"] = False
        _search_state["region"] = ""


def run_queue(regions: list[str]):
    """Process multiple regions sequentially."""
    _search_state["queue"] = list(regions)
    _search_state["queue_total"] = len(regions)
    _search_state["queue_done"] = 0
    for region in regions:
        run_search(region)
        _search_state["queue_done"] += 1
    _search_state["queue"] = []
    _search_state["queue_total"] = 0
    _search_state["queue_done"] = 0


def _check_website(name: str, region: str) -> dict:
    """Search Google for the business and check if it has a real website."""
    query = f'"{name}" {region}'
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = httpx.get(
                "https://www.google.com/search",
                params={"q": query, "num": 10, "hl": "de"},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=15,
                follow_redirects=True,
                verify=False,
            )
        resp.raise_for_status()
    except Exception as e:
        return {"has_website": False, "url": None, "error": str(e)}

    html = resp.text
    # Extract URLs from Google results
    urls = re.findall(r'https?://[^\s"<>]+', html)

    for url in urls:
        # Extract domain
        match = re.match(r'https?://(?:www\.)?([^/]+)', url)
        if not match:
            continue
        domain = match.group(1).lower()

        # Skip known directories and Google's own URLs
        if any(d in domain for d in DIRECTORY_DOMAINS):
            continue
        if "google" in domain:
            continue

        # Looks like a real business website
        clean_url = re.match(r'(https?://[^&"]+)', url)
        if clean_url:
            return {"has_website": True, "url": clean_url.group(1)}

    return {"has_website": False, "url": None}


security = HTTPBasic()

AUTH_USER = os.environ.get("AUTH_USER", "admin")
AUTH_PASS = os.environ.get("AUTH_PASS", "changeme")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode(), AUTH_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), AUTH_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan, dependencies=[Depends(verify_credentials)])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/businesses")
def list_businesses(
    status: str | None = Query(None),
    region: str | None = Query(None),
    category: str | None = Query(None),
):
    return get_businesses(status=status, region=region, category=category)


@app.post("/search")
def trigger_search(payload: SearchPayload):
    if not payload.region.strip():
        raise HTTPException(400, "Region cannot be empty")
    thread = threading.Thread(target=run_search, args=(payload.region.strip(),), daemon=True)
    thread.start()
    return {"message": f"Search started for '{payload.region}'"}


@app.post("/search/queue")
def trigger_queue(payload: QueuePayload):
    regions = [r.strip() for r in payload.regions if r.strip()]
    if not regions:
        raise HTTPException(400, "No valid regions provided")
    if _search_state["searching"]:
        raise HTTPException(409, "A search is already running")
    thread = threading.Thread(target=run_queue, args=(regions,), daemon=True)
    thread.start()
    return {"message": f"Queue started: {len(regions)} regions", "regions": regions}


@app.get("/search/status")
def search_status():
    return {
        "searching": _search_state["searching"],
        "region": _search_state["region"],
        "queue_total": _search_state["queue_total"],
        "queue_done": _search_state["queue_done"],
    }


@app.get("/businesses/{business_id}/draft-email")
def draft_email(business_id: int):
    """Generate a personalized cold email for a business."""
    biz = get_business(business_id)
    if not biz:
        raise HTTPException(404, "Business not found")

    name = biz["name"]
    category = biz.get("category", "Unternehmen") or "Unternehmen"
    region = biz.get("region", "") or ""
    email = biz.get("email", "") or ""

    # German category labels for nicer text
    cat_labels = {
        "restaurant": "Restaurants", "cafe": "Cafés", "bar": "Bars", "pub": "Lokale",
        "fast_food": "Schnellrestaurants", "bakery": "Bäckereien", "butcher": "Metzgereien",
        "hairdresser": "Friseure", "beauty": "Beauty-Salons", "dentist": "Zahnarztpraxen",
        "doctors": "Arztpraxen", "pharmacy": "Apotheken", "hotel": "Hotels",
        "car_repair": "Autowerkstätten", "electrician": "Elektriker", "plumber": "Installateure",
        "florist": "Blumenläden", "optician": "Optiker",
    }
    cat_label = cat_labels.get(category.lower(), category.capitalize())

    subject = f"Website für {name} in {region}?" if region else f"Website für {name}?"

    body = (
        f"Guten Tag,\n\n"
        f"ich bin auf Ihr Geschäft \"{name}\" aufmerksam geworden und habe gesehen, "
        f"dass Sie derzeit keine eigene Website haben.\n\n"
        f"Viele Kunden suchen heute online nach {cat_label}"
        + (f" in {region}" if region else "")
        + f" — ohne Website gehen Ihnen potenzielle Kunden verloren.\n\n"
        f"Ich erstelle professionelle Websites speziell für {cat_label} und würde Ihnen "
        f"gerne zeigen, wie Ihre Online-Präsenz aussehen könnte.\n\n"
        f"Darf ich Ihnen ein unverbindliches Beispiel zusenden?\n\n"
        f"Mit freundlichen Grüßen"
    )

    return {"subject": subject, "body": body, "email": email}


@app.patch("/businesses/{business_id}")
def update(business_id: int, payload: UpdatePayload):
    update_business(
        business_id,
        status=payload.status,
        notes=payload.notes,
        follow_up=payload.follow_up,
    )
    return {"ok": True}


@app.post("/businesses/{business_id}/verify")
def verify_website(business_id: int):
    """Check if a business now has a website via Google search."""
    biz = get_business(business_id)
    if not biz:
        raise HTTPException(404, "Business not found")

    result = _check_website(biz["name"], biz.get("region", ""))

    if result.get("has_website") and result.get("url"):
        update_business(
            business_id,
            status="Has Website",
            website_url=result["url"],
        )

    return result


@app.delete("/businesses/{business_id}")
def delete(business_id: int):
    delete_business(business_id)
    return {"ok": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
