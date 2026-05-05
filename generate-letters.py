"""
generate-letters.py — Sub-step 3 of the letter pipeline.

Local script. Renders PDFs for Phase 1 leads, uploads each to the Railway
`letters` table via /api/letters/create, and mirrors them to letters/pending/
for visual review in File Explorer.

Usage:
    # Pre-flight (no DB writes, no uploads):
    python generate-letters.py --dry-run

    # Live:
    python generate-letters.py

    # Re-render specific codes only (e.g. after a fix):
    python generate-letters.py --codes VB02,VB06

Required environment (defaults shown):
    RAILWAY_BASE_URL       https://handwerkerweb.at
    AUTH_USER              admin
    AUTH_PASS              p3t5o1STv09bGJioKl6PJA   (set in Railway env)
    TRACKING_DOMAIN        https://handwerkerweb.at
    ABSENDER_NAME          Felix Gmeiner
    ABSENDER_STRASSE       Dorfstraße 41
    ABSENDER_PLZ_ORT       6713 Ludesch
    ABSENDER_EMAIL         felix.gmeiner18@gmail.com
    ABSENDER_TELEFON       +43 676 6505015
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import date
from pathlib import Path

# render_letter.py lives in the renderer patch folder. Add it to sys.path so
# this script works when run from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent
_RENDERER_DIR = _REPO_ROOT / "Felix AI Brain" / "03 Projects" / "Automatic Webside Seller" / "05 System" / "patches" / "2026-05-03-renderer"
sys.path.insert(0, str(_RENDERER_DIR))

import httpx                                                # noqa: E402
from render_letter import (                                 # noqa: E402
    Absender,
    Lead,
    PHASE_1_LEADS,
    TEMPLATE_VERSION,
    render_letter,
    render_to_file,
)

# ─── Config ─────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = os.environ.get("RAILWAY_BASE_URL", "https://handwerkerweb.at")
DEFAULT_AUTH_USER = os.environ.get("AUTH_USER", "admin")
DEFAULT_AUTH_PASS = os.environ.get("AUTH_PASS", "")
DEFAULT_TRACKING_DOMAIN = os.environ.get("TRACKING_DOMAIN", "https://handwerkerweb.at")

PENDING_DIR = _REPO_ROOT / "letters" / "pending"
HTTP_TIMEOUT = 30.0


# ─── Core ───────────────────────────────────────────────────────────────────

def upload_letter(
    base_url: str,
    auth: tuple[str, str],
    business_id: int,
    tracking_code: str,
    template_version: str,
    pdf_bytes: bytes,
) -> dict:
    """POST a generated PDF to /api/letters/create. Returns the JSON response.

    Raises if the response isn't 2xx (with the API's error body in the message).
    """
    url = f"{base_url.rstrip('/')}/api/letters/create"
    body = {
        "business_id": business_id,
        "tracking_code": tracking_code,
        "template_version": template_version,
        "pdf_bytes_b64": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    with httpx.Client(timeout=HTTP_TIMEOUT, auth=auth) as client:
        r = client.post(url, json=body)
    if r.status_code == 409:
        # tracking_code already exists in DB — surface as a soft skip
        raise LetterAlreadyExists(r.json().get("detail", str(r.status_code)))
    if not r.is_success:
        raise RuntimeError(f"POST {url} → HTTP {r.status_code}: {r.text}")
    return r.json()


class LetterAlreadyExists(Exception):
    """Server returned 409 Conflict — tracking_code already in letters table."""
    pass


def generate_one(
    lead: Lead,
    absender: Absender,
    tracking_domain: str,
    base_url: str,
    auth: tuple[str, str],
    *,
    dry_run: bool = False,
) -> dict:
    """Render one lead's PDF, save locally, upload to Railway. Returns a result dict."""
    if not lead.business_id:
        raise ValueError(f"{lead.code}: business_id is required")

    tracking_url = f"{tracking_domain.rstrip('/')}/{lead.code}"
    pdf_bytes = render_letter(lead, absender, tracking_url, on_date=date.today())

    # Mirror to local file for File Explorer review
    local_path = render_to_file(lead, absender, tracking_url, PENDING_DIR)

    if dry_run:
        return {
            "code": lead.code,
            "firma": lead.firma,
            "business_id": lead.business_id,
            "pdf_bytes": len(pdf_bytes),
            "local": str(local_path),
            "uploaded": False,
            "letter_id": None,
            "skipped": False,
        }

    try:
        resp = upload_letter(
            base_url=base_url,
            auth=auth,
            business_id=lead.business_id,
            tracking_code=lead.code,
            template_version=TEMPLATE_VERSION,
            pdf_bytes=pdf_bytes,
        )
        return {
            "code": lead.code,
            "firma": lead.firma,
            "business_id": lead.business_id,
            "pdf_bytes": len(pdf_bytes),
            "local": str(local_path),
            "uploaded": True,
            "letter_id": resp["letter_id"],
            "skipped": False,
        }
    except LetterAlreadyExists as e:
        return {
            "code": lead.code,
            "firma": lead.firma,
            "business_id": lead.business_id,
            "pdf_bytes": len(pdf_bytes),
            "local": str(local_path),
            "uploaded": False,
            "letter_id": None,
            "skipped": True,
            "skip_reason": str(e),
        }


# ─── CLI ────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="Render Phase 1 letter PDFs and upload to Railway letters table.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Render PDFs and save locally but don't upload to Railway.")
    parser.add_argument("--codes", default="",
                        help="Comma-separated tracking codes to render (default: all 8).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--user", default=DEFAULT_AUTH_USER)
    parser.add_argument("--password", default=DEFAULT_AUTH_PASS,
                        help="Basic auth password (defaults to AUTH_PASS env var).")
    parser.add_argument("--tracking-domain", default=DEFAULT_TRACKING_DOMAIN)
    args = parser.parse_args()

    if not args.dry_run and not args.password:
        sys.exit("ERROR: --password (or AUTH_PASS env var) is required for live uploads.")

    # Filter leads
    if args.codes:
        wanted = {c.strip().upper() for c in args.codes.split(",") if c.strip()}
        leads = [l for l in PHASE_1_LEADS if l.code in wanted]
        missing = wanted - {l.code for l in leads}
        if missing:
            sys.exit(f"ERROR: Unknown codes: {sorted(missing)}")
    else:
        leads = list(PHASE_1_LEADS)

    absender = Absender.from_env()
    auth = (args.user, args.password)

    print(f"Generating {len(leads)} letter(s).")
    print(f"  base_url        : {args.base_url}")
    print(f"  tracking_domain : {args.tracking_domain}")
    print(f"  absender        : {absender.name} <{absender.email}>")
    print(f"  pending dir     : {PENDING_DIR}")
    print(f"  dry_run         : {args.dry_run}")
    print()

    results = []
    failures = []
    for lead in leads:
        try:
            r = generate_one(
                lead=lead,
                absender=absender,
                tracking_domain=args.tracking_domain,
                base_url=args.base_url,
                auth=auth,
                dry_run=args.dry_run,
            )
            results.append(r)
            if r["skipped"]:
                print(f"  SKIP  {r['code']}  {r['firma']:<48}  "
                      f"({r.get('skip_reason', 'already exists')})")
            elif r["uploaded"]:
                print(f"  OK    {r['code']}  {r['firma']:<48}  "
                      f"letter_id={r['letter_id']}  ({r['pdf_bytes']:,} bytes)")
            else:
                print(f"  DRY   {r['code']}  {r['firma']:<48}  "
                      f"({r['pdf_bytes']:,} bytes, not uploaded)")
        except Exception as e:
            failures.append((lead.code, str(e)))
            print(f"  FAIL  {lead.code}  {lead.firma}  -- {e}")

    print()
    n_ok = sum(1 for r in results if r["uploaded"])
    n_skip = sum(1 for r in results if r["skipped"])
    n_dry = sum(1 for r in results if not r["uploaded"] and not r["skipped"])
    print(f"Summary: {n_ok} uploaded, {n_skip} skipped, {n_dry} dry-run, {len(failures)} failed.")
    if failures:
        sys.exit(1)
    print()
    print("Next: open the PDFs in", PENDING_DIR, "for visual review.")
    if not args.dry_run:
        print("After review, run approve.ps1 / reject.ps1 (sub-step 4).")


if __name__ == "__main__":
    _cli()
