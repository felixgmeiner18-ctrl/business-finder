import base64
import io
import json
import os
import re
import secrets
import threading
import warnings
import zipfile
from contextlib import asynccontextmanager

import anthropic
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.requests import Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import (
    delete_business,
    get_business,
    get_businesses,
    get_settings,
    init_db,
    save_contact_submission,
    save_settings,
    update_business,
    update_site_info,
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


class GeneratePayload(BaseModel):
    business_id: int


class ExportPayload(BaseModel):
    business_id: int
    html: str
    theme: str = ""
    sections: list = []


class ContactPayload(BaseModel):
    name: str
    email: str
    phone: str = ""
    message: str


class SettingsPayload(BaseModel):
    sender_name: str = ""
    sender_company: str = "PageBuilder"
    sender_email: str = ""
    sender_phone: str = ""


def _build_generator_prompt(biz: dict) -> str:
    name = biz.get("name", "")
    category = biz.get("category", "business") or "business"
    region = biz.get("region", "Deutschland") or "Deutschland"
    phone = biz.get("phone", "") or ""
    address = biz.get("address", "") or ""
    return f"""You are a world-class web designer creating a premium website for a German small business.

Business: {name}
Industry: {category}
City: {region}
Phone: {phone}
Address: {address}

Design a genuinely high-end, unique website. Avoid generic designs.
Think: what visual identity would make this specific {category} business feel premium, trustworthy, and memorable to German customers?

Available Google Font pairings (choose one):
- Playfair Display + Lato
- Cormorant Garamond + Raleway
- Fraunces + Inter
- DM Serif Display + DM Sans
- Libre Baskerville + Source Sans Pro
- Josefin Sans + Montserrat
- Crimson Pro + Work Sans
- Outfit + Plus Jakarta Sans

Layout variants (choose one per section):
- hero: full-bleed-atmospheric | split-cinematic | minimal-centered
- services: card-grid | icon-columns | horizontal-feature
- about: split-portrait-story | centered-founder | full-text-elegant
- contact: phone-prominent | minimal-form | split-with-info

Choose design_tokens to reflect the brand personality:
- border_radius: 0px = sharp/editorial, 4px = professional, 12px = modern, 99px = playful/pill
- button_style: solid = confident, outline = refined, soft-shadow = warm, minimalist = typographic

Return ONLY valid JSON (no markdown, no explanation):
{{
  "personality": "3-word brand character",
  "mood": "one evocative sentence describing the visual feeling",
  "theme": "slug-style-theme-name",
  "colors": {{
    "primary": "#hexcolor",
    "accent": "#hexcolor",
    "background": "#hexcolor",
    "surface": "#hexcolor",
    "text": "#hexcolor",
    "text_muted": "#hexcolor"
  }},
  "fonts": {{
    "heading": "Google Font Name",
    "body": "Google Font Name"
  }},
  "design_tokens": {{
    "border_radius": "CSS value: 0px | 4px | 12px | 99px",
    "button_style": "solid | outline | soft-shadow | minimalist"
  }},
  "animations": "brief animation style description",
  "decorative_style": "brief decorative element description",
  "sections": ["hero", "services", "about", "contact"],
  "layout": {{
    "hero": "chosen-variant",
    "services": "chosen-variant",
    "about": "chosen-variant",
    "contact": "chosen-variant"
  }},
  "copy": {{
    "business_name": "{name}",
    "headline": "compelling German headline (not generic, specific to this type of business)",
    "tagline": "short evocative German tagline",
    "services": [
      {{"name": "Leistung 1", "description": "1-2 authentic Sätze auf Deutsch", "icon": "relevant emoji"}},
      {{"name": "Leistung 2", "description": "1-2 authentic Sätze auf Deutsch", "icon": "relevant emoji"}},
      {{"name": "Leistung 3", "description": "1-2 authentic Sätze auf Deutsch", "icon": "relevant emoji"}}
    ],
    "about": "2-3 warm, authentic Sätze auf Deutsch",
    "cta": "Handlungsaufforderung auf Deutsch",
    "phone": "{phone}",
    "address": "{address}"
  }},
  "seo": {{
    "meta_title": "Optimized page title max 60 chars",
    "meta_description": "Compelling German meta description max 155 chars"
  }}
}}"""


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


AUTH_USER = os.environ.get("AUTH_USER", "admin")
AUTH_PASS = os.environ.get("AUTH_PASS", "changeme")

_UNAUTH = Response(
    content="Unauthorized",
    status_code=401,
    headers={"WWW-Authenticate": 'Basic realm="Business Finder"'},
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


PUBLIC_PATHS = {"/", "/health", "/api/contact"}


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return _UNAUTH
    try:
        user, pw = base64.b64decode(auth[6:]).decode().split(":", 1)
    except Exception:
        return _UNAUTH
    if not (secrets.compare_digest(user, AUTH_USER) and secrets.compare_digest(pw, AUTH_PASS)):
        return _UNAUTH
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def portfolio():
    return FileResponse("static/portfolio.html")


@app.get("/admin")
def admin_dashboard():
    return FileResponse("static/index.html")


@app.get("/businesses")
def list_businesses(
    status: str | None = Query(None),
    region: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    return get_businesses(status=status, region=region, category=category, limit=limit, offset=offset)


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


CATEGORY_HOOKS = {
    "restaurant": {
        "benefit": "Online-Reservierungen, eine ansprechende Speisekarte und aktuelle Öffnungszeiten",
        "stat": "Über 70 % der Gäste schauen sich ein Restaurant online an, bevor sie hingehen",
    },
    "cafe": {
        "benefit": "Öffnungszeiten, eine einladende Speisekarte und Fotos Ihres Cafés",
        "stat": "Die meisten Gäste suchen online nach Cafés in der Nähe",
    },
    "hairdresser": {
        "benefit": "Online-Terminbuchung, eine aktuelle Preisliste und eine Galerie Ihrer Arbeiten",
        "stat": "Über 60 % der Kunden buchen Friseur-Termine heute online",
    },
    "beauty": {
        "benefit": "Online-Terminbuchung, eine Vorher-Nachher-Galerie und Ihre Behandlungsübersicht",
        "stat": "Die meisten Neukunden suchen Beauty-Salons zuerst im Internet",
    },
    "dentist": {
        "benefit": "Online-Terminanfragen, Informationen zu Leistungen und ein vertrauenswürdiger erster Eindruck",
        "stat": "9 von 10 Patienten suchen ihren Zahnarzt über Google",
    },
    "doctors": {
        "benefit": "Online-Terminanfragen, aktuelle Sprechzeiten und Informationen zu Ihren Leistungen",
        "stat": "Die Mehrheit der Patienten informiert sich online, bevor sie eine Praxis aufsucht",
    },
    "hotel": {
        "benefit": "Direktbuchungen ohne Provision — das spart Ihnen 15–20 % gegenüber Booking-Portalen",
        "stat": "Viele Gäste buchen lieber direkt, wenn eine gute Website vorhanden ist",
    },
    "car_repair": {
        "benefit": "Online-Terminvereinbarung, Kundenbewertungen und eine Übersicht Ihrer Leistungen",
        "stat": "Die meisten Autofahrer suchen ihre Werkstatt heute online",
    },
    "bakery": {
        "benefit": "eine Produktübersicht, Bestellmöglichkeit und Ihre Öffnungszeiten",
        "stat": "Kunden erwarten auch von lokalen Bäckereien eine Online-Präsenz",
    },
    "florist": {
        "benefit": "Online-Bestellung, Lieferservice-Infos und eine Galerie Ihrer Arrangements",
        "stat": "Ein Großteil der Blumenbestellungen beginnt heute mit einer Google-Suche",
    },
    "electrician": {
        "benefit": "Notdienst-Kontaktmöglichkeit, Referenzen und eine Übersicht Ihrer Leistungen",
        "stat": "Im Notfall suchen Kunden zuerst online nach einem Elektriker in der Nähe",
    },
    "plumber": {
        "benefit": "Notdienst-Kontaktmöglichkeit, Referenzen und eine Übersicht Ihrer Leistungen",
        "stat": "Im Notfall suchen Kunden zuerst online nach einem Installateur in der Nähe",
    },
    "pharmacy": {
        "benefit": "Notdienst-Zeiten, Vorbestellmöglichkeit und aktuelle Informationen",
        "stat": "Immer mehr Kunden prüfen Apotheken-Angebote und Notdienste online",
    },
    "optician": {
        "benefit": "Online-Terminvereinbarung, eine Brillen-Galerie und Ihre Leistungsübersicht",
        "stat": "Viele Kunden vergleichen Optiker online, bevor sie sich entscheiden",
    },
}
_DEFAULT_HOOK = {
    "benefit": "aktuelle Informationen, Kontaktmöglichkeiten und einen professionellen ersten Eindruck",
    "stat": "Über 80 % der Kunden informieren sich heute online, bevor sie ein Geschäft aufsuchen",
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

    hook = CATEGORY_HOOKS.get(category.lower(), _DEFAULT_HOOK)

    subject = f"Mehr Kunden für {name} in {region}? So geht's." if region else f"Mehr Kunden für {name}? So geht's."

    # Build signature from settings
    settings = get_settings()
    sig_lines = []
    if settings.get("sender_name"):
        sig_lines.append(settings["sender_name"])
    if settings.get("sender_company"):
        sig_lines.append(f"{settings['sender_company']} — Webentwicklung")
    if settings.get("sender_email"):
        sig_lines.append(settings["sender_email"])
    if settings.get("sender_phone"):
        sig_lines.append(settings["sender_phone"])
    signature = "\n".join(sig_lines)

    body = (
        f"Guten Tag,\n\n"
        f"ich habe nach {cat_label} in {region} gesucht und bin dabei auf "
        f"\"{name}\" gestoßen — allerdings ohne eigene Website.\n\n"
        f"{hook['stat']}. Ohne Website sind Sie für "
        f"diese Kunden praktisch unsichtbar.\n\n"
        f"Dabei könnte eine professionelle Website für Sie so viel leisten: "
        f"{hook['benefit']}.\n\n"
        f"Ich habe bereits eine Beispiel-Website speziell für Ihr Geschäft "
        f"vorbereitet, damit Sie sehen können, wie Ihr Auftritt aussehen könnte.\n\n"
        f"Soll ich Ihnen diese kostenlos und unverbindlich zusenden?\n\n"
        f"Mit freundlichen Grüßen"
    )

    if signature:
        body += f"\n\n{signature}"

    return {"subject": subject, "body": body, "email": email}


@app.get("/api/settings")
def read_settings():
    return get_settings()


@app.put("/api/settings")
def write_settings(payload: SettingsPayload):
    save_settings(payload.model_dump())
    return {"ok": True}


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


@app.get("/admin/generator")
def generator_page():
    return FileResponse("static/generator.html")


@app.post("/api/contact")
async def submit_contact(payload: ContactPayload):
    if not payload.name.strip() or not payload.email.strip() or not payload.message.strip():
        raise HTTPException(400, "Name, E-Mail und Nachricht sind erforderlich")
    save_contact_submission(payload.name.strip(), payload.email.strip(), payload.phone.strip(), payload.message.strip())
    return {"ok": True}


@app.post("/api/generator/generate")
async def generate_site(payload: GeneratePayload):
    biz = get_business(payload.business_id)
    if not biz:
        raise HTTPException(404, "Business not found")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set in environment variables")

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        prompt = _build_generator_prompt(biz)

        message = await client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        spec = json.loads(raw)
        update_site_info(payload.business_id, spec.get("theme", ""), json.dumps(spec.get("sections", [])))
        return spec
    except anthropic.AuthenticationError:
        raise HTTPException(500, "ANTHROPIC_API_KEY is invalid — check the value in Railway")
    except anthropic.APIError as e:
        raise HTTPException(500, f"Anthropic API error: {e}")
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse AI response as JSON: {e}")


@app.post("/api/generator/export")
async def export_site(payload: ExportPayload):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", payload.html)
        zf.writestr(
            "README.txt",
            "Website Export\n\nDateien:\n- index.html: Öffnen Sie diese Datei im Browser\n\n"
            "Für die Veröffentlichung laden Sie index.html auf Ihren Webserver hoch.\n",
        )
    buf.seek(0)
    theme_slug = re.sub(r"[^a-z0-9-]", "", (payload.theme or "website").lower()) or "website"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=website-{theme_slug}.zip"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
