"""
render_letter.py — Sub-step 2 of the letter pipeline.

Pure renderer. Takes a lead dict + sender details, returns PDF bytes.
No DB. No API calls. No file IO except optionally writing the PDF to disk.

Usage (CLI):
    python render_letter.py --self-test
    python render_letter.py --code VB02 --out ./out

Usage (library):
    from render_letter import render_letter, Lead
    pdf_bytes = render_letter(lead, absender, tracking_url)
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional

import qrcode
import qrcode.image.svg
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from weasyprint import HTML

# ─── Constants ──────────────────────────────────────────────────────────────

# Map OSM-style category to "Laienbegriff" (what trades-people call themselves)
KATEGORIE_LAIE_MAP = {
    "carpenter":          "Tischler",
    "electrician":        "Elektriker",
    "plumber":            "Installateur",
    "painter":            "Maler",
    "locksmith":          "Schlosser",
    "metal_construction": "Metallbauer",
    "roofer":             "Dachdecker",
    "heating_engineer":   "Heizungsbauer",
    "tiler":              "Fliesenleger",
    "stonemason":         "Steinmetz",
    "plasterer":          "Verputzer",
    "floorer":            "Bodenleger",
    "handyman":           "Handwerker",
    "gasfitter":          "Gas-Installateur",
    "glazier":            "Glaser",
    "hvac":               "Installateur",  # informal — close enough
}

DEFAULT_REGION = "Vorarlberg"
TEMPLATE_FILENAME = "letter_template.html"
TEMPLATE_VERSION = "v1"


# ─── Data shapes ────────────────────────────────────────────────────────────

@dataclass
class Lead:
    """One recipient. Field names match the (C) Letter v1 — DE Trades.md schema."""
    firma: str
    strasse: str          # Straße + Hausnummer, no city
    plz: str              # 4-digit AT postal code
    ort: str              # City
    kategorie: str        # OSM key (carpenter, electrician, ...) OR override label
    code: str             # Tracking code, e.g. "VB02"
    business_id: Optional[int] = None     # FK into businesses table (used by
                                          # generate-letters.py to link the
                                          # letters row to its source business)
    kategorie_laie_override: Optional[str] = None  # set when OSM category is wrong
                                                    # (e.g. VB06 Hämmerle is actually
                                                    # Elektrotechniker, OSM said locksmith)


@dataclass
class Absender:
    """Sender block. Loaded from env vars by default."""
    name: str
    strasse: str
    plz_ort: str
    email: str
    telefon: str = ""
    land: str = "Österreich"
    ort: str = "Ludesch"  # for the "Ludesch, 03.05.2026" line above the subject

    @classmethod
    def from_env(cls) -> "Absender":
        return cls(
            name    = os.environ.get("ABSENDER_NAME",    "Felix Gmeiner"),
            strasse = os.environ.get("ABSENDER_STRASSE", "Dorfstraße 41"),
            plz_ort = os.environ.get("ABSENDER_PLZ_ORT", "6713 Ludesch"),
            email   = os.environ.get("ABSENDER_EMAIL",   "felix.gmeiner18@gmail.com"),
            telefon = os.environ.get("ABSENDER_TELEFON", "+43 676 6505015"),
            land    = os.environ.get("ABSENDER_LAND",    "Österreich"),
            ort     = os.environ.get("ABSENDER_ORT",     "Ludesch"),
        )


# ─── Rendering ──────────────────────────────────────────────────────────────

def _kategorie_laie(lead: Lead) -> str:
    """Return the Laien-friendly category word for the letter hook."""
    if lead.kategorie_laie_override:
        return lead.kategorie_laie_override
    return KATEGORIE_LAIE_MAP.get(lead.kategorie.lower(), "Handwerker")


def _qr_code_svg(payload: str) -> Markup:
    """
    Build a QR code as inline SVG (vector — stays crisp at print resolution).
    Returns a Jinja-safe Markup object so the SVG isn't HTML-escaped in the
    template. We strip the XML declaration so the SVG embeds cleanly inside HTML.

    Error-correction level M = 15% data redundancy. Letterxpress prints in
    300 DPI, so M is plenty robust for a 22-24mm code on a printed letter.
    """
    qr = qrcode.QRCode(
        version=None,                                  # auto-pick smallest fit
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")

    # Strip XML declaration; CSS controls size via the wrapper.
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    # Drop the hardcoded width/height so CSS sizes the SVG.
    svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    return Markup(svg)


def _format_date_de(d: date) -> str:
    """German date format: 03.05.2026"""
    return d.strftime("%d.%m.%Y")


def _jinja_env(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render_letter(
    lead: Lead,
    absender: Absender,
    tracking_url: str,
    *,
    on_date: Optional[date] = None,
    template_dir: Optional[Path] = None,
    region: str = DEFAULT_REGION,
) -> bytes:
    """
    Render a single letter to PDF bytes.

    `tracking_url` should already include the lead's code, e.g.
        https://website-check.at/VB02
    Caller is responsible for assembling it.
    """
    if on_date is None:
        on_date = date.today()
    if template_dir is None:
        template_dir = Path(__file__).resolve().parent

    env = _jinja_env(template_dir)
    template = env.get_template(TEMPLATE_FILENAME)

    context = {
        # recipient
        "firma":              lead.firma,
        "empfaenger_strasse": lead.strasse,
        "empfaenger_plz":     lead.plz,
        "empfaenger_ort":     lead.ort,
        "kategorie_laie":     _kategorie_laie(lead),

        # sender
        "absender_name":    absender.name,
        "absender_strasse": absender.strasse,
        "absender_plz_ort": absender.plz_ort,
        "absender_email":   absender.email,
        "absender_telefon": absender.telefon,
        "ort_absender":     absender.ort,

        # letter meta
        "datum":           _format_date_de(on_date),
        "region":          region,
        "tracking_url":    tracking_url,
        "tracking_code":   lead.code,
        "tracking_qr_svg": _qr_code_svg(tracking_url),
        "template_version": TEMPLATE_VERSION,
    }

    html_str = template.render(**context)
    pdf_bytes = HTML(string=html_str, base_url=str(template_dir)).write_pdf()
    return pdf_bytes


def render_to_file(
    lead: Lead,
    absender: Absender,
    tracking_url: str,
    out_dir: Path,
    *,
    on_date: Optional[date] = None,
) -> Path:
    """Render and write to {out_dir}/{CODE}_{firma_slug}.pdf. Returns the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = render_letter(lead, absender, tracking_url, on_date=on_date)
    slug = _slug(lead.firma)
    out_path = out_dir / f"{lead.code}_{slug}.pdf"
    out_path.write_bytes(pdf_bytes)
    return out_path


def _slug(text: str) -> str:
    """Filename-safe slug. Keeps it human-readable."""
    repl = {"ä":"ae","ö":"oe","ü":"ue","Ä":"Ae","Ö":"Oe","Ü":"Ue","ß":"ss"}
    for k, v in repl.items():
        text = text.replace(k, v)
    safe = []
    for ch in text:
        if ch.isalnum():
            safe.append(ch)
        elif ch in (" ", "-", "_"):
            safe.append("_")
    return "".join(safe).strip("_")[:60]


# ─── Phase 1 send-list (sub-step 2 self-test data) ──────────────────────────

PHASE_1_LEADS = [
    # business_id values come from `(C) Phase 1 Send List.md` — the manually-
    # curated list, post Google-verifier audit. Don't change without re-checking.
    Lead("Benzer Schlosserei-Metallbau",            "Radetzkystraße 66", "6845", "Hohenems", "locksmith",          "VB01", business_id=3454),
    Lead("Tischlerei Brändle",                       "Achstraße 45",      "6844", "Altach",   "carpenter",          "VB02", business_id=3448),
    Lead("Sieghartsleitner Tischlerei & Parkettverlegung","Industriestraße 6","6832","Sulz",   "carpenter",          "VB03", business_id=3446),
    Lead("Ammann Josef Haustechnik",                 "Feldgasse 15",      "6840", "Götzis",   "plumber",            "VB04", business_id=3445),
    Lead("Micheluzzi",                               "Industriestraße 9", "6971", "Hard",     "painter",            "VB05", business_id=3435),
    Lead("Hämmerle Elmar eh-mechatronik",            "Schwefel 91a",      "6850", "Dornbirn", "locksmith",          "VB06", business_id=3424,
         kategorie_laie_override="Elektrotechniker"),
    Lead("Lampl Energie- und Gebäudetechnik",        "Flurstraße 2",      "6833", "Klaus",    "plumber",            "VB07", business_id=3419),
    Lead("Ladurner",                                  "Kesselstraße 27b", "6922", "Wolfurt",  "metal_construction", "VB08", business_id=3455),
]


# ─── CLI ────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(description="Render letter PDFs (sub-step 2 self-test).")
    parser.add_argument("--code", help="Tracking code (e.g. VB02). If omitted, all 8 are rendered.")
    parser.add_argument("--out", default="./out", help="Output directory (default ./out).")
    parser.add_argument(
        "--tracking-domain",
        default=os.environ.get("TRACKING_DOMAIN", "https://handwerkerweb.at"),
        help="Tracking URL prefix. Per-letter code is appended.",
    )
    parser.add_argument("--self-test", action="store_true",
                        help="Render VB02 (Tischlerei Brändle) and assert basic invariants.")
    args = parser.parse_args()

    absender = Absender.from_env()
    out_dir = Path(args.out).resolve()

    if args.self_test:
        return _self_test(absender, args.tracking_domain, out_dir)

    leads = (
        [l for l in PHASE_1_LEADS if l.code == args.code]
        if args.code else PHASE_1_LEADS
    )
    if not leads:
        sys.exit(f"No lead with code {args.code!r}. Known: {[l.code for l in PHASE_1_LEADS]}")

    written = []
    for lead in leads:
        url = f"{args.tracking_domain.rstrip('/')}/{lead.code}"
        path = render_to_file(lead, absender, url, out_dir)
        written.append(path)
        print(f"  OK {lead.code}  {lead.firma:<48}  -> {path.name}")
    print(f"\nWrote {len(written)} PDF(s) to {out_dir}/")


def _self_test(absender: Absender, tracking_domain: str, out_dir: Path) -> None:
    """Render VB02 and check basic invariants. Exits non-zero on failure."""
    print("Self-test: rendering VB02 (Tischlerei Brändle)...")
    lead = next(l for l in PHASE_1_LEADS if l.code == "VB02")
    url = f"{tracking_domain.rstrip('/')}/{lead.code}"
    pdf_bytes = render_letter(lead, absender, url)

    # Invariants
    assert pdf_bytes.startswith(b"%PDF-"),                 "not a PDF"
    assert len(pdf_bytes) > 5_000,                         f"PDF suspiciously small ({len(pdf_bytes)} bytes)"
    assert len(pdf_bytes) < 500_000,                       f"PDF suspiciously large ({len(pdf_bytes)} bytes)"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "VB02_self_test.pdf"
    out_path.write_bytes(pdf_bytes)

    print(f"  OK PDF written:  {out_path}  ({len(pdf_bytes):,} bytes)")
    print(f"  OK Tracking URL: {url}")
    print(f"  OK Kategorie:    {_kategorie_laie(lead)}")
    print(f"  OK Telefon:      {absender.telefon or '(none)'}")
    print("Open the PDF and verify visually:")
    print("  - Recipient address sits inside the window-envelope frame")
    print("  - Umlaute render correctly: 'Brändle', 'Achstraße'")
    print("  - Subject reads: 'Eine Website für Tischlerei Brändle'")
    print("  - QR code present beside the tracking URL")
    print("  - Tracking URL on the page ends in /VB02")
    print("  - Phone number appears in the contact line at the bottom")


if __name__ == "__main__":
    _cli()
