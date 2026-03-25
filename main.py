import base64
import io
import json
import os
import random
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


DESIGN_PHILOSOPHIES = [
    {
        "name": "Glassmorphism",
        "description": "Frosted-glass panels, translucent layers, soft depth and blur effects over gradient backgrounds",
        "color_approach": "Deep gradient background (dark indigo/purple or navy). Surface cards semi-transparent with backdrop-blur. Accent in bright cyan, white, or electric violet.",
        "typography_mood": "Light-weight clean sans-serif headings. Body text readable against glass. Avoid heavy strokes.",
        "animation_style": "Soft fade-ins, gentle parallax on glass layers, subtle shimmer on hover, blurred entrance animations",
        "forbidden": "No flat white backgrounds, no heavy solid borders, no traditional card boxes",
    },
    {
        "name": "Bold Editorial",
        "description": "Large display typography dominates the layout — editorial newspaper meets modern digital magazine",
        "color_approach": "High contrast base: near-black or pure white. One vivid accent (electric red, cobalt, mustard yellow). Monochrome with one pop.",
        "typography_mood": "Oversized serif or display font for headings (think 80–120px). Tight letter-spacing. Body in a clean, narrow sans.",
        "animation_style": "Staggered word-by-word reveal, horizontal slide-ins, bold underline draw animations",
        "forbidden": "No rounded soft cards, no pastel color schemes, no generic hero image layouts",
    },
    {
        "name": "Luxe Dark",
        "description": "Ultra-premium dark aesthetic — the feeling of a luxury brand boutique or a five-star hotel lobby",
        "color_approach": "Deep charcoal or near-black background. Gold (#C9A84C), champagne, or dusty rose as accent. Muted warm off-whites for text.",
        "typography_mood": "Refined serif for headings (Cormorant, Didot style). Light tracking, generous line-height. Whisper of elegance.",
        "animation_style": "Slow, deliberate fade-ins. Gold line reveals. Subtle scroll parallax. Nothing rushed.",
        "forbidden": "No bright white backgrounds, no playful rounded shapes, no neon or vibrant colors",
    },
    {
        "name": "Japandi Minimal",
        "description": "Japanese-Scandinavian fusion: clean function, warm silence, natural materials — digital wabi-sabi",
        "color_approach": "Warm off-white or linen background (#F5F0E8). Stone grey, muted sage, warm taupe. One restrained accent (terracotta or forest green).",
        "typography_mood": "Delicate, light-weight serif or minimal sans. Wide letter-spacing. Short lines. Intentional emptiness.",
        "animation_style": "Whisper-quiet fade-ins. No bounce, no scale. Elements arrive like morning light.",
        "forbidden": "No bright colors, no thick borders, no clutter, no dense text blocks",
    },
    {
        "name": "Soft Gradient",
        "description": "Dreamy pastel gradients as the core aesthetic — soft, contemporary, and approachable",
        "color_approach": "Gradient backgrounds blending 2–3 soft pastels (lavender→peach, mint→sky, rose→lilac). White surface cards. Accent in the deepest gradient hue.",
        "typography_mood": "Modern rounded sans-serif. Friendly, warm. Medium weight headings. Body text in dark charcoal for contrast.",
        "animation_style": "Floating elements, gentle upward drifts, smooth gradient color transitions on scroll",
        "forbidden": "No dark mode, no hard edges, no heavy shadows, no stark black-and-white contrast",
    },
    {
        "name": "Neo-Brutalist",
        "description": "Raw, unapologetic design — thick black borders, high contrast, unconventional grid breaks",
        "color_approach": "Stark white or cream base. Black borders (3–5px). 1–2 bold accent colors (yellow, hot pink, lime green). Nothing subtle.",
        "typography_mood": "Black, heavy sans-serif headings. Uppercase or mixed-case. Body in a utilitarian grotesque.",
        "animation_style": "Jerky entrance animations, offset shadow reveals, bold transform on hover",
        "forbidden": "No gentle gradients, no rounded corners, no subtle anything — everything is intentional and loud",
    },
    {
        "name": "Organic Natural",
        "description": "Earth-toned warmth inspired by natural materials — wood, stone, clay, living plants",
        "color_approach": "Warm earthy background (sand, parchment, warm cream). Olive green, terracotta, warm brown as accents. Never cold or clinical.",
        "typography_mood": "Organic serif or slightly irregular humanist font. Warm, approachable. Like a handwritten note turned digital.",
        "animation_style": "Slow, organic reveals — like plants growing. Soft parallax on texture backgrounds.",
        "forbidden": "No cold blues or greys, no sharp geometric precision, no corporate feel",
    },
    {
        "name": "Swiss International",
        "description": "Strict Swiss grid system — precision typography, geometric structure, intellectual clarity",
        "color_approach": "White background. Black type. One pure accent color (red, cyan, or cobalt). Zero decoration — only structure.",
        "typography_mood": "Helvetica-inspired or geometric sans-serif. Rigid baseline grid. No ornament, only information hierarchy.",
        "animation_style": "Grid-aligned slide-ins, clean opacity fades, type size transitions on scroll",
        "forbidden": "No serifs, no gradients, no decorative elements — grid and type ARE the design",
    },
    {
        "name": "Art Deco Revival",
        "description": "1920s glamour reimagined for the digital age — geometric ornament, symmetry, metallic luxury",
        "color_approach": "Deep navy or black background. Gold, champagne, and ivory as primary palette. Rich jewel tones (emerald, burgundy) as accents.",
        "typography_mood": "Geometric serif with high contrast strokes. Uppercase headlines. Ornate but controlled.",
        "animation_style": "Symmetrical reveal animations, golden line draws, chevron transitions",
        "forbidden": "No casual or rounded fonts, no flat minimal approach, no pastel colors",
    },
    {
        "name": "Retro Modern",
        "description": "Warm 1970s–80s aesthetics fused with contemporary UX — nostalgic yet completely usable",
        "color_approach": "Warm off-white or cream base. Burnt orange, avocado green, warm brown, brick red as palette. Feels like a vintage poster.",
        "typography_mood": "Retro slab-serif or display type with a vintage flavor. Body in a clean readable sans.",
        "animation_style": "Slight rotations, typewriter text reveals, retro-style slide transitions",
        "forbidden": "No cold modern blues, no glassmorphism, no slick techy aesthetics",
    },
    {
        "name": "Nordic Minimal",
        "description": "Scandinavian functional design — cool clarity, purposeful whitespace, understated sophistication",
        "color_approach": "Pure white or very light grey (#F8F9FA) background. Cool slate, steel blue, ash grey as accents. Minimal color use.",
        "typography_mood": "Clean, neutral grotesque sans-serif. Medium weight. Functional, never decorative.",
        "animation_style": "Crisp, fast fade-ins. Subtle upward movement. No theatrics.",
        "forbidden": "No warm tones, no ornament, no expressive typography — restrained elegance only",
    },
    {
        "name": "Coastal Luxury",
        "description": "Light, airy, premium — the aesthetic of a Mediterranean coastal resort or boutique beach hotel",
        "color_approach": "Soft white or sandy linen base. Muted ocean blue (#7BA7BC), warm sand (#E8D5B0), driftwood grey. Airy and spacious.",
        "typography_mood": "Elegant light-weight serif for headings. Airy tracking. Body in a clean readable sans.",
        "animation_style": "Floating fade-ins, gentle wave-like stagger, slow parallax on imagery",
        "forbidden": "No dark heavy backgrounds, no urban industrial feel, no neon",
    },
    {
        "name": "Dark Tech",
        "description": "Sleek dark-mode interface with neon accents — the aesthetic of cutting-edge software and digital innovation",
        "color_approach": "Deep dark background (#0D1117 or #111827). Neon cyan (#00F5FF), electric green, or violet as accent. Subtle glow effects.",
        "typography_mood": "Geometric monospace or technical sans-serif. Cool, precise, efficient.",
        "animation_style": "Glitch reveals, neon glow pulses, scan-line effects, data-stream animations",
        "forbidden": "No warm earthy tones, no serif fonts, no soft pastels",
    },
    {
        "name": "Memphis Pop",
        "description": "Bold geometric shapes, vibrant colors, pattern-driven — like a postmodern 80s design studio",
        "color_approach": "Vibrant multicolor palette: hot pink, cobalt, yellow, black. Geometric pattern accents. High energy.",
        "typography_mood": "Bold, expressive display fonts. Mixed weights. Fun but structured.",
        "animation_style": "Bouncy entrances, rotation reveals, pattern layer animations",
        "forbidden": "No muted or minimal color schemes, no corporate restraint",
    },
    {
        "name": "Neumorphism",
        "description": "Soft extruded UI — elements appear pressed from or raised out of the background material",
        "color_approach": "Single-hue monochromatic palette (light grey, warm white, or soft blue). Shadows in two tones (light + dark of same hue). Extremely subtle.",
        "typography_mood": "Clean sans-serif, medium weight. Color matches the palette exactly. No harsh contrast.",
        "animation_style": "Pressed-in button states, soft glow on focus, gentle elevation changes",
        "forbidden": "No high contrast, no gradients from different hues, no multi-color schemes",
    },
    {
        "name": "Cinematic Dark",
        "description": "Film-inspired dramatic composition — spotlight effects, deep blacks, wide-screen proportions",
        "color_approach": "Near-black background (#0A0A0A). One spotlight color (amber, crimson, ice blue) for hero accent. Muted tones throughout.",
        "typography_mood": "Wide-tracked uppercase sans or bold cinematic serif. Dramatic scale contrast between heading and body.",
        "animation_style": "Spotlight fade-ins, dramatic scale reveals, slow parallax pan effects",
        "forbidden": "No light backgrounds, no cheerful colors, no small modest typography",
    },
    {
        "name": "Biophilic Design",
        "description": "Nature-connected design — organic shapes, living greens, texture-rich and calming",
        "color_approach": "Deep forest green (#1B4332), sage (#8FAF8A), warm cream. Earthy browns as neutrals. Feels like a forest walk.",
        "typography_mood": "Organic humanist serif or warm rounded sans. Flowing, unhurried.",
        "animation_style": "Leaf-fall stagger reveals, organic curve path transitions, slow breathing scale animations",
        "forbidden": "No stark white or cold grey, no tech-industrial aesthetic, no sharp geometric shapes",
    },
    {
        "name": "Kinetic Motion-First",
        "description": "Animation is the design — every element enters with purpose, scroll triggers narrative reveals",
        "color_approach": "Clean, high-contrast base (white or dark) so animations stand out. 1–2 vivid accent colors for motion emphasis.",
        "typography_mood": "Bold, expressive type that participates in animation. Words as visual objects.",
        "animation_style": "Scroll-triggered word splits, velocity-based parallax layers, staggered character reveals, kinetic scroll progress indicators",
        "forbidden": "No static flat layouts, no decorative elements that don't animate, no gentle fades without intention",
    },
]

FONT_PAIRINGS = [
    ("Playfair Display", "Lato"),
    ("Cormorant Garamond", "Raleway"),
    ("Fraunces", "Inter"),
    ("DM Serif Display", "DM Sans"),
    ("Libre Baskerville", "Source Sans Pro"),
    ("Josefin Sans", "Montserrat"),
    ("Crimson Pro", "Work Sans"),
    ("Outfit", "Plus Jakarta Sans"),
    ("Bebas Neue", "Open Sans"),
    ("Bodoni Moda", "Mulish"),
    ("Anton", "Roboto"),
    ("Yeseva One", "Nunito"),
    ("Space Grotesk", "Space Mono"),
    ("Italiana", "Jost"),
    ("Syne", "Karla"),
    ("Abril Fatface", "Poppins"),
    ("Marcellus SC", "Lora"),
    ("Urbanist", "Figtree"),
    ("Unbounded", "IBM Plex Sans"),
    ("Gloock", "Satoshi"),
    ("Tenor Sans", "Quicksand"),
    ("Rufina", "Fira Sans"),
]

LAYOUT_VARIANTS = {
    "hero": [
        "full-bleed-atmospheric",
        "split-cinematic",
        "minimal-centered",
        "bold-typographic",
        "asymmetric-split",
        "overlay-gradient",
    ],
    "services": [
        "card-grid",
        "icon-columns",
        "horizontal-feature",
        "bento-grid",
        "numbered-list",
        "alternating-rows",
    ],
    "about": [
        "split-portrait-story",
        "centered-founder",
        "full-text-elegant",
        "timeline-story",
        "stat-highlights",
    ],
    "contact": [
        "phone-prominent",
        "minimal-form",
        "split-with-info",
        "full-width-cta-banner",
        "card-with-address",
    ],
}


def _get_industry_hint(category: str, style_name: str) -> str:
    hints = {
        "restaurant": f"Industry note: With {style_name}, ensure the design evokes appetite and warmth. Food and atmosphere should be central to the visual narrative.",
        "cafe": f"Industry note: Apply {style_name} to create a sense of coziness and daily ritual. The space between elements should breathe like a calm morning.",
        "arzt": f"Industry note: With {style_name}, maintain clarity and trust above all. Patients must feel safe, competent care is nearby.",
        "zahnarzt": f"Industry note: {style_name} applied to a dental practice — cleanliness and precision should feel reassuring, not clinical.",
        "friseur": f"Industry note: {style_name} for a salon — lean into personal transformation, style identity, and the confidence of a great cut.",
        "kosmetik": f"Industry note: With {style_name}, radiate self-care, elegance, and the quiet luxury of personal attention.",
        "hotel": f"Industry note: {style_name} for a hotel — every pixel should whisper 'welcome home'. Comfort, experience, and anticipation.",
        "bakery": f"Industry note: Apply {style_name} to evoke warmth, craft, and the pleasure of fresh-baked goods. Texture and warmth matter.",
        "bäcker": f"Industry note: Apply {style_name} to evoke warmth, craft, and the pleasure of fresh-baked goods. Texture and warmth matter.",
        "florist": f"Industry note: {style_name} for a florist — color, organic shapes, and the ephemeral beauty of flowers should guide every decision.",
        "blumen": f"Industry note: {style_name} for a florist — color, organic shapes, and the ephemeral beauty of flowers should guide every decision.",
        "autowerkstatt": f"Industry note: {style_name} applied to an auto workshop — precision, reliability, and technical confidence are key signals.",
        "elektriker": f"Industry note: With {style_name}, project technical expertise and dependability. Customers trust you with their home's safety.",
        "klempner": f"Industry note: {style_name} for a plumber — fast, dependable, professional. Urgency and reliability in visual balance.",
        "rechtsanwalt": f"Industry note: With {style_name}, gravitas and precision matter. This is a practice where trust is the core product.",
        "steuerberater": f"Industry note: {style_name} applied to a tax consultancy — intellectual rigor, reliability, and the relief of being in good hands.",
        "physiotherapie": f"Industry note: With {style_name}, project healing, movement, and the body in balance. Warmth and professionalism coexist.",
        "fitness": f"Industry note: {style_name} for a fitness studio — energy, transformation, and the satisfying burn of a great workout.",
    }
    cat_lower = (category or "").lower()
    for key, hint in hints.items():
        if key in cat_lower:
            return hint
    return f"Industry note: Apply {style_name} in a way that builds immediate trust and a strong local identity for {category} customers in Germany."


def _build_generator_prompt(biz: dict) -> str:
    name = biz.get("name", "")
    category = biz.get("category", "business") or "business"
    region = biz.get("region", "Deutschland") or "Deutschland"
    phone = biz.get("phone", "") or ""
    address = biz.get("address", "") or ""

    style = random.choice(DESIGN_PHILOSOPHIES)
    heading_font, body_font = random.choice(FONT_PAIRINGS)
    industry_hint = _get_industry_hint(category, style["name"])

    layout_options = "\n".join(
        f"- {section}: {' | '.join(variants)}"
        for section, variants in LAYOUT_VARIANTS.items()
    )

    return f"""You are a world-class web designer creating a premium, one-of-a-kind website for a German small business.

Business: {name}
Industry: {category}
City: {region}
Phone: {phone}
Address: {address}

━━━ YOUR DESIGN DIRECTION ━━━
Style: {style["name"]}
Philosophy: {style["description"]}
Color Approach: {style["color_approach"]}
Typography Mood: {style["typography_mood"]}
Animation Style: {style["animation_style"]}
Constraint: {style["forbidden"]}

{industry_hint}

━━━ FONTS (use exactly this pairing) ━━━
Heading: {heading_font}
Body: {body_font}

━━━ LAYOUT VARIANTS (choose one per section) ━━━
{layout_options}

━━━ DESIGN TOKENS ━━━
- border_radius: 0px = sharp/editorial | 4px = professional | 8px = rounded | 12px = modern | 99px = pill/playful
- button_style: solid | outline | soft-shadow | minimalist | pill-gradient

━━━ MANDATORY RULES ━━━
1. This design MUST embody {style["name"]} deeply — not as decoration, but as its entire visual DNA.
2. Colors must follow the {style["name"]} Color Approach above. Do not default to what is typical for {category}.
3. Every copy line must be specific to {name} in {region}, written in German. Zero filler or placeholder text.
4. Sections may appear in any order — hero must be first. Be intentional about sequence.
5. The result must look nothing like a generic business website template.

Return ONLY valid JSON (no markdown, no explanation):
{{
  "personality": "3-word brand character reflecting {style["name"]}",
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
    "heading": "{heading_font}",
    "body": "{body_font}"
  }},
  "design_tokens": {{
    "border_radius": "CSS value",
    "button_style": "chosen-style"
  }},
  "animations": "specific animation description matching {style["name"]}",
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
}}


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
