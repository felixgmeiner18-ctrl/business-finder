"""
send-approved.py — Sub-step 5 of the letter pipeline.

Ships every `status='approved'` letter from the Railway letters table to
Letterxpress, then transitions each row to `sent` with the Letterxpress
transaction_id recorded for audit.

Usage:
    # Check Letterxpress balance + auth (no sends):
    python send-approved.py --balance

    # Dry-run: simulate the send pipeline without calling Letterxpress:
    python send-approved.py --dry-run

    # Send only specific codes:
    python send-approved.py --codes VB01,VB03

    # Live send everything in 'approved':
    python send-approved.py

Required env vars:
    LETTERXPRESS_USERNAME   (your Letterxpress account email)
    LETTERXPRESS_API_KEY    (generated in Letterxpress account settings)
    AUTH_PASS               (admin password for Railway API)

Optional env vars:
    RAILWAY_BASE_URL        default: https://handwerkerweb.at
    AUTH_USER               default: admin
    LETTERXPRESS_API_URL    default: https://api.letterxpress.de/v2
    LETTERXPRESS_COLOR      default: "1" (1=b/w, 4=color)
    LETTERXPRESS_MODE       default: "simplex" (one-sided)
    LETTERXPRESS_SHIP       default: "national" (within AT/DE)

Pricing (Letterxpress, ~2026):
    DIN A4 b/w national: ~€0.89 per letter
    8 letters = ~€7.12 (well within the €15 prefunded balance)
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import date
from pathlib import Path

# render_letter.py lives next to this script
_REPO_ROOT = Path(__file__).resolve().parent

import httpx
from render_letter import Absender, Lead, PHASE_1_LEADS

# ─── Config ─────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = os.environ.get("RAILWAY_BASE_URL", "https://handwerkerweb.at")
DEFAULT_AUTH_USER = os.environ.get("AUTH_USER", "admin")
DEFAULT_AUTH_PASS = os.environ.get("AUTH_PASS", "")
DEFAULT_LX_USER = os.environ.get("LETTERXPRESS_USERNAME", "")
DEFAULT_LX_KEY = os.environ.get("LETTERXPRESS_API_KEY", "")
DEFAULT_LX_URL = os.environ.get("LETTERXPRESS_API_URL", "https://api.letterxpress.de/v2")
DEFAULT_COLOR = os.environ.get("LETTERXPRESS_COLOR", "1")        # 1 = b/w
DEFAULT_MODE = os.environ.get("LETTERXPRESS_MODE", "simplex")    # one-sided
DEFAULT_SHIP = os.environ.get("LETTERXPRESS_SHIP", "national")   # within AT/DE

HTTP_TIMEOUT = 60.0
EXPECTED_PRICE_PER_LETTER_EUR = 0.89


# ─── Letterxpress API client ────────────────────────────────────────────────

class LetterxpressError(Exception):
    """Raised when Letterxpress returns a non-success response."""
    pass


def lx_balance(api_url: str, lx_user: str, lx_key: str) -> dict:
    """GET balance from Letterxpress. Returns {"balance": float, "currency": "EUR"}
    or raises LetterxpressError."""
    url = f"{api_url.rstrip('/')}/balance"
    body = {"auth": {"username": lx_user, "apikey": lx_key}}
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.post(url, json=body)
    if not r.is_success:
        raise LetterxpressError(f"balance check failed: HTTP {r.status_code} :: {r.text}")
    data = r.json()
    # Letterxpress responses tend to wrap data — try common shapes:
    if isinstance(data, dict):
        if "balance" in data:
            return {"balance": float(data["balance"]), "currency": data.get("currency", "EUR")}
        if "data" in data and isinstance(data["data"], dict) and "balance" in data["data"]:
            return {"balance": float(data["data"]["balance"]), "currency": data["data"].get("currency", "EUR")}
    raise LetterxpressError(f"unexpected balance response shape: {data}")


def lx_submit_letter(
    api_url: str,
    lx_user: str,
    lx_key: str,
    pdf_bytes: bytes,
    *,
    color: str = DEFAULT_COLOR,
    mode: str = DEFAULT_MODE,
    ship: str = DEFAULT_SHIP,
) -> str:
    """Submit one PDF to Letterxpress /setJob. Returns the transaction_id."""
    url = f"{api_url.rstrip('/')}/setJob"
    body = {
        "auth": {"username": lx_user, "apikey": lx_key},
        "letter": {
            "base64_file": base64.b64encode(pdf_bytes).decode("ascii"),
            "base64_filetype": "pdf",
            "specification": {
                "color": color,
                "mode": mode,
                "ship": ship,
            },
        },
    }
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.post(url, json=body)
    if not r.is_success:
        raise LetterxpressError(f"setJob failed: HTTP {r.status_code} :: {r.text}")
    data = r.json()
    # Try common response shapes for the transaction_id:
    candidates = [
        data.get("letter", {}).get("id"),
        data.get("letter", {}).get("letter_id"),
        data.get("data", {}).get("id"),
        data.get("data", {}).get("letter_id"),
        data.get("id"),
        data.get("letter_id"),
    ]
    for c in candidates:
        if c is not None:
            return str(c)
    raise LetterxpressError(f"setJob success but no transaction_id in response: {data}")


# ─── Railway API client ─────────────────────────────────────────────────────

def rw_list_approved(base_url: str, auth: tuple[str, str]) -> list[dict]:
    """GET /api/letters?status=approved → list of metadata rows."""
    url = f"{base_url.rstrip('/')}/api/letters?status=approved"
    with httpx.Client(timeout=HTTP_TIMEOUT, auth=auth) as client:
        r = client.get(url)
    r.raise_for_status()
    return r.json().get("rows", [])


def rw_get_letter_pdf(base_url: str, auth: tuple[str, str], letter_id: int) -> bytes:
    """GET /api/letters/{id}/pdf → raw PDF bytes."""
    url = f"{base_url.rstrip('/')}/api/letters/{letter_id}/pdf"
    with httpx.Client(timeout=HTTP_TIMEOUT, auth=auth) as client:
        r = client.get(url)
    r.raise_for_status()
    return r.content


def rw_mark_sent(base_url: str, auth: tuple[str, str], letter_id: int, transaction_id: str) -> dict:
    """POST /api/letters/{id}/sent with the Letterxpress transaction_id."""
    url = f"{base_url.rstrip('/')}/api/letters/{letter_id}/sent"
    with httpx.Client(timeout=HTTP_TIMEOUT, auth=auth) as client:
        r = client.post(url, json={"transaction_id": transaction_id})
    r.raise_for_status()
    return r.json()


def rw_mark_failed(base_url: str, auth: tuple[str, str], letter_id: int, reason: str) -> dict:
    """POST /api/letters/{id}/failed with the error reason."""
    url = f"{base_url.rstrip('/')}/api/letters/{letter_id}/failed"
    with httpx.Client(timeout=HTTP_TIMEOUT, auth=auth) as client:
        r = client.post(url, json={"reason": reason})
    r.raise_for_status()
    return r.json()


# ─── Helpers ────────────────────────────────────────────────────────────────

def lead_for(tracking_code: str) -> Lead | None:
    """Find the matching Lead in PHASE_1_LEADS by tracking code."""
    for l in PHASE_1_LEADS:
        if l.code == tracking_code:
            return l
    return None


# ─── Main CLI ───────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(description="Ship approved letters via Letterxpress.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be sent and the estimated cost. No Letterxpress calls, no DB transitions.")
    parser.add_argument("--balance", action="store_true",
                        help="Just check Letterxpress balance + auth. No sends.")
    parser.add_argument("--codes", default="",
                        help="Comma-separated tracking codes to send (default: all approved).")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--user", default=DEFAULT_AUTH_USER)
    parser.add_argument("--password", default=DEFAULT_AUTH_PASS, help="Admin password (defaults to AUTH_PASS env var).")
    parser.add_argument("--lx-username", default=DEFAULT_LX_USER, help="Letterxpress account email.")
    parser.add_argument("--lx-apikey", default=DEFAULT_LX_KEY, help="Letterxpress API key.")
    parser.add_argument("--lx-api-url", default=DEFAULT_LX_URL)
    args = parser.parse_args()

    # ─── Pre-flight ────────────────────────────────────────────────────────
    if not args.lx_username or not args.lx_apikey:
        sys.exit("ERROR: Set LETTERXPRESS_USERNAME and LETTERXPRESS_API_KEY env vars (or use --lx-username/--lx-apikey).")

    # ─── --balance mode ────────────────────────────────────────────────────
    if args.balance:
        print(f"Checking Letterxpress balance at {args.lx_api_url}...")
        try:
            b = lx_balance(args.lx_api_url, args.lx_username, args.lx_apikey)
            print(f"  Balance: {b['balance']:.2f} {b['currency']}")
            print(f"  At ~€{EXPECTED_PRICE_PER_LETTER_EUR:.2f}/letter, that's ~{int(b['balance']/EXPECTED_PRICE_PER_LETTER_EUR)} letters.")
        except LetterxpressError as e:
            sys.exit(f"ERROR: {e}")
        return

    # All other modes require Railway auth
    if not args.password:
        sys.exit("ERROR: --password (or AUTH_PASS env var) is required for send modes.")
    auth = (args.user, args.password)

    # ─── Fetch the approved letters ────────────────────────────────────────
    print(f"Fetching approved letters from {args.base_url}...")
    try:
        approved = rw_list_approved(args.base_url, auth)
    except httpx.HTTPError as e:
        sys.exit(f"ERROR fetching approved letters: {e}")

    # Filter by --codes if given
    if args.codes:
        wanted = {c.strip().upper() for c in args.codes.split(",") if c.strip()}
        approved = [l for l in approved if l["tracking_code"] in wanted]
        missing = wanted - {l["tracking_code"] for l in approved}
        if missing:
            print(f"  WARNING: not in approved: {sorted(missing)}")

    if not approved:
        print("Nothing to send.")
        return

    # ─── Preview ───────────────────────────────────────────────────────────
    print()
    print(f"=== About to send {len(approved)} letter(s) ===")
    total_pages = 0
    missing_leads = []
    for row in approved:
        code = row["tracking_code"]
        lead = lead_for(code)
        if lead is None:
            missing_leads.append(code)
            print(f"  ?? {code}  letter_id={row['id']}  -- NO MATCHING Lead in PHASE_1_LEADS")
            continue
        print(f"  -> {code}  letter_id={row['id']:<3}  {lead.firma:<48}  {lead.strasse}, {lead.plz} {lead.ort}")
        total_pages += 1

    if missing_leads:
        sys.exit(f"\nERROR: {len(missing_leads)} letter(s) have no matching Lead in PHASE_1_LEADS: {missing_leads}\n"
                 f"This script only handles Phase 1 leads. Add them to PHASE_1_LEADS or skip with --codes.")

    estimated_eur = total_pages * EXPECTED_PRICE_PER_LETTER_EUR
    print(f"\nEstimated cost: ~€{estimated_eur:.2f}  ({total_pages} × €{EXPECTED_PRICE_PER_LETTER_EUR:.2f})")
    print(f"Letterxpress endpoint: {args.lx_api_url}/setJob")
    print(f"Print options: color={DEFAULT_COLOR} ({'b/w' if DEFAULT_COLOR == '1' else 'color'}), mode={DEFAULT_MODE}, ship={DEFAULT_SHIP}")

    # ─── --dry-run mode ────────────────────────────────────────────────────
    if args.dry_run:
        print("\nDRY RUN — no letters sent, no DB transitions.")
        return

    # ─── Live: confirmation prompt ─────────────────────────────────────────
    print()
    print(f"!! This will submit {len(approved)} real letters to Letterxpress and bill ~€{estimated_eur:.2f}.")
    confirm = input("Type 'send' to confirm, anything else to cancel: ").strip().lower()
    if confirm != "send":
        print("Cancelled.")
        return

    # ─── Optional: pre-check balance ───────────────────────────────────────
    try:
        b = lx_balance(args.lx_api_url, args.lx_username, args.lx_apikey)
        if b["balance"] < estimated_eur:
            sys.exit(f"ERROR: Letterxpress balance {b['balance']:.2f} {b['currency']} is below estimated cost €{estimated_eur:.2f}. Top up first.")
        print(f"\nLetterxpress balance OK: {b['balance']:.2f} {b['currency']}")
    except LetterxpressError as e:
        print(f"WARNING: could not pre-check balance ({e}). Proceeding anyway.")

    # ─── Live send loop ────────────────────────────────────────────────────
    print()
    ok = 0
    fail = 0
    for row in approved:
        code = row["tracking_code"]
        letter_id = row["id"]
        try:
            # Download PDF from Railway
            pdf_bytes = rw_get_letter_pdf(args.base_url, auth, letter_id)
            # Submit to Letterxpress
            txn_id = lx_submit_letter(args.lx_api_url, args.lx_username, args.lx_apikey, pdf_bytes)
            # Mark as sent in Railway DB
            rw_mark_sent(args.base_url, auth, letter_id, txn_id)
            print(f"  SENT  {code}  letter_id={letter_id:<3}  transaction_id={txn_id}")
            ok += 1
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            print(f"  FAIL  {code}  letter_id={letter_id}  -- {reason}")
            try:
                rw_mark_failed(args.base_url, auth, letter_id, reason[:500])
            except Exception as e2:
                print(f"        (also failed to mark as failed: {e2})")
            fail += 1

    print()
    print(f"Summary: {ok} sent, {fail} failed.")
    if fail > 0:
        sys.exit(1)
    print()
    print("Next:")
    print("  - Letterxpress prints + posts next business day.")
    print("  - 3-4 week response window starts.")
    print("  - Monitor: GET /api/contact/list for form submissions, your inbox for direct replies.")


if __name__ == "__main__":
    _cli()
