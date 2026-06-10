"""Lead qualification: hard disqualifiers, postcode repair, quality scoring.

The pipeline is postal-only — a lead without a mailable street address is
worthless no matter what else it has. Everything here exists so Felix only
ever reviews leads that are worth his time.

Stages (used by verify-local.py):
  1. hard_disqualify()  — unmailable / junk-name leads → auto-reject reason
  2. repair_postcode()  — derive missing PLZ from the town in the address
  3. score()            — 1-10 quality score → stored as `priority`
"""

import re

# Vorarlberg town → PLZ. Covers every town that has shown up in scrapes;
# extend as new towns appear (towns with several PLZ get the main one).
VLBG_PLZ = {
    "bregenz": "6900", "hard": "6971", "lauterach": "6923", "wolfurt": "6922",
    "kennelbach": "6921", "schwarzach": "6858", "bildstein": "6858",
    "hoechst": "6973", "höchst": "6973", "fussach": "6972", "fußach": "6972",
    "gaissau": "6974", "gaißau": "6974", "hoerbranz": "6912", "hörbranz": "6912",
    "lochau": "6911", "eichenberg": "6911", "moeggers": "6900", "möggers": "6900",
    "dornbirn": "6850", "lustenau": "6890", "hohenems": "6845", "altach": "6844",
    "goetzis": "6840", "götzis": "6840", "maeder": "6841", "mäder": "6841",
    "koblach": "6842", "klaus": "6833", "weiler": "6837", "fraxern": "6833",
    "sulz": "6832", "roethis": "6832", "röthis": "6832", "zwischenwasser": "6835",
    "rankweil": "6830", "uebersaxen": "6830", "übersaxen": "6830",
    "feldkirch": "6800", "meiningen": "6812", "goefis": "6811", "göfis": "6811",
    "satteins": "6822", "schlins": "6824", "frastanz": "6820", "nenzing": "6710",
    "duens": "6822", "düns": "6822", "schnifis": "6822", "roens": "6822", "röns": "6822",
    "ludesch": "6713", "bludesch": "6719", "thueringen": "6712", "thüringen": "6712",
    "bludenz": "6700", "nueziders": "6714", "nüziders": "6714", "buers": "6706",
    "bürs": "6706", "buerserberg": "6707", "bürserberg": "6707", "brand": "6708",
    "stallehr": "6700", "loruens": "6700", "lorüns": "6700", "innerbraz": "6751",
    "dalaas": "6752", "kloesterle": "6754", "klösterle": "6754",
    "schruns": "6780", "tschagguns": "6774", "vandans": "6773", "bartholomaeberg": "6781",
    "bartholomäberg": "6781", "silbertal": "6782", "st. gallenkirch": "6791",
    "gaschurn": "6793", "st. anton im montafon": "6771",
    "egg": "6863", "andelsbuch": "6866", "bezau": "6870", "schwarzenberg": "6867",
    "alberschwende": "6861", "lingenau": "6951", "hittisau": "6952",
    "krumbach": "6942", "langenegg": "6941", "doren": "6933", "sulzberg": "6934",
    "riefensberg": "6943", "mellau": "6881", "au": "6883", "schoppernau": "6886",
    "damuels": "6884", "damüls": "6884", "warth": "6767", "lech": "6764",
    "raggal": "6741", "sonntag": "6731", "fontanella": "6733", "blons": "6723",
    "st. gerold": "6721", "thueringerberg": "6721", "thüringerberg": "6721",
}

# Words that signal a real business name (vs. a bare OSM label like "Maler")
TRADE_WORDS = re.compile(
    r"tischler|schreiner|installat|elektro|holzbau|zimmer|spengler|maler|"
    r"dach|metall|schlosser|stein|fliesen|glas|boden|heizung|sanitaer|sanitär|"
    r"haustechnik|gebaeude|gebäude|energie|montage|bau|technik|werkstatt",
    re.IGNORECASE)
LEGAL_FORMS = re.compile(r"\b(gmbh|og|kg|e\.?u\.?|ges\.?m\.?b\.?h\.?)\b", re.IGNORECASE)
# A bare trade word as the whole name = OSM junk ("Maler", "Decker", …)
JUNK_NAMES = {"maler", "decker", "summer", "eisenhauer", "tischler", "elektriker",
              "installateur", "schlosser", "zimmerer", "spengler", "bodenleger"}


def find_town(address: str) -> str | None:
    """Find a known Vorarlberg town in the address string (longest match)."""
    low = " " + address.lower().strip() + " "
    hit = None
    for town in VLBG_PLZ:
        if f" {town} " in low or low.endswith(f" {town} "):
            if hit is None or len(town) > len(hit):
                hit = town
    return hit


def has_street(address: str) -> bool:
    """A mailable address needs a street part with a house number."""
    if not address or address.strip().upper() in ("", "N/A"):
        return False
    return bool(re.search(r"\d", address))  # house number somewhere


def hard_disqualify(lead: dict) -> str | None:
    """Return a rejection reason, or None if the lead survives."""
    name = (lead.get("name") or "").strip()
    address = (lead.get("address") or "").strip()
    if not has_street(address):
        return "keine Postadresse im Datensatz (Brief unzustellbar)"
    if name.lower() in JUNK_NAMES or len(name) < 4:
        return f"Name '{name}' ist ein OSM-Platzhalter, kein Betriebsname"
    return None


def repair_postcode(lead: dict) -> str | None:
    """Derive the PLZ from the town if it's missing. Returns new PLZ or None."""
    if (lead.get("postal_code") or "").strip():
        return None
    town = find_town(lead.get("address") or "")
    return VLBG_PLZ.get(town) if town else None


def score(lead: dict, exists: bool | None = None) -> int:
    """Quality score 1-10 → stored as priority. Higher = review first."""
    s = 0
    name = (lead.get("name") or "")
    address = (lead.get("address") or "")
    if has_street(address):
        s += 3
    if (lead.get("postal_code") or "").strip():
        s += 2
    if (lead.get("phone") or "").strip():
        s += 1
    if (lead.get("email") or "").strip():
        s += 1
    if TRADE_WORDS.search(name) or LEGAL_FORMS.search(name):
        s += 2
    elif len(name.split()) >= 2:
        s += 1
    if exists is True:
        s += 1
    return max(1, min(10, s))
