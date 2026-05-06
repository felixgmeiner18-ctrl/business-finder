# Phase 1 Send List — 8 letters, Vorarlberg trades

**Compiled:** 2026-04-23
**Source:** OSM scrape of Vorarlberg (`niche=trades`), manually verified by Felix to have no real website.
**Batch:** #1 — baseline response-rate test.

## The 8

All 8 resolved from DB (pulled 2026-04-23). Addresses normalized from OSM `address` field (street + house number split from trailing city name).

| # | ID | Business | Kategorie (Laie) | Straße | PLZ | Ort | Code |
|---|---:|---|---|---|---:|---|---|
| 1 | 3454 | Benzer Schlosserei-Metallbau | Schlosser | Radetzkystraße 66 | 6845 | Hohenems | VB01 |
| 2 | 3448 | Tischlerei Brändle | Tischler | Achstraße 45 | 6844 | Altach | VB02 |
| 3 | 3446 | Sieghartsleitner Tischlerei & Parkettverlegung | Tischler | Industriestraße 6 | 6832 | Sulz | VB03 |
| 4 | 3445 | Ammann Josef Haustechnik | Installateur | Feldgasse 15 | 6840 | Götzis | VB04 |
| 5 | 3435 | Micheluzzi | Maler | Industriestraße 9 | 6971 | Hard | VB05 |
| 6 | 3424 | Hämmerle Elmar eh-mechatronik | Elektrotechniker ⚠ | Schwefel 91a | 6850 | Dornbirn | VB06 |
| 7 | 3419 | Lampl Energie- und Gebäudetechnik | Installateur | Flurstraße 2 | 6833 | Klaus | VB07 |
| 8 | 3455 | Ladurner | Metallbauer | Kesselstraße 27b | 6922 | Wolfurt | VB08 |

**Tracking codes:** `VB01`–`VB08`. Each letter carries its own code in the CTA URL (`{{TRACKING_URL}}/VBxx`). Replies are attributed by which code was used.

### Category overrides (important)

- **#6 Hämmerle Elmar eh-mechatronik** — OSM tagged as `locksmith`, but business name signals Elektrotechnik/Mechatronik. Letter copy should say "Elektrotechniker" in the hook, not "Schlosser". Flagged with ⚠ above.
- **#8 Ladurner** — OSM `metal_construction` → "Metallbauer" (not "Schlosser"). Correct in the table.

### Address format notes

- OSM stored addresses as "StraßeName Hausnummer Ort" with no comma separator — I split on the last whitespace to isolate the city.
- ID 3455 Ladurner: OSM had "Kesselstraße 27b;27a" (building spans two numbers). Using `27b` as primary; postal carrier finds the building regardless.
- UTF-8 is clean in the DB. PowerShell's `Format-Table` display mangles ß/ä/ö/ü but the underlying bytes are correct. Python mail-merge will render properly.

## Mail-merge payload (ready to hand to print-API)

```yaml
- firma: "Benzer Schlosserei-Metallbau"
  strasse: "Radetzkystraße 66"
  plz: "6845"
  ort: "Hohenems"
  kategorie: "Schlosser"
  code: "VB01"
- firma: "Tischlerei Brändle"
  strasse: "Achstraße 45"
  plz: "6844"
  ort: "Altach"
  kategorie: "Tischler"
  code: "VB02"
- firma: "Sieghartsleitner Tischlerei & Parkettverlegung"
  strasse: "Industriestraße 6"
  plz: "6832"
  ort: "Sulz"
  kategorie: "Tischler"
  code: "VB03"
- firma: "Ammann Josef Haustechnik"
  strasse: "Feldgasse 15"
  plz: "6840"
  ort: "Götzis"
  kategorie: "Installateur"
  code: "VB04"
- firma: "Micheluzzi"
  strasse: "Industriestraße 9"
  plz: "6971"
  ort: "Hard"
  kategorie: "Maler"
  code: "VB05"
- firma: "Hämmerle Elmar eh-mechatronik"
  strasse: "Schwefel 91a"
  plz: "6850"
  ort: "Dornbirn"
  kategorie: "Elektrotechniker"
  code: "VB06"
- firma: "Lampl Energie- und Gebäudetechnik"
  strasse: "Flurstraße 2"
  plz: "6833"
  ort: "Klaus"
  kategorie: "Installateur"
  code: "VB07"
- firma: "Ladurner"
  strasse: "Kesselstraße 27b"
  plz: "6922"
  ort: "Wolfurt"
  kategorie: "Metallbauer"
  code: "VB08"
```

## Pre-flight checklist (MUST be done before mailing)

- [x] **Street addresses filled in** — done 2026-04-23, all 8 resolved.
- [ ] **Print-API picked** (Pingen vs Letterxpress — Task #4)
- [ ] **Tracking domain bought** — `handwerkerweb.at` (picked 2026-05-03, world4you, €12 first year)
- [ ] **Landing page live** at `{domain}/VBxx` — one form: Firma, Name, Telefon, kurze Beschreibung. Logs visit + form submit.
- [ ] **Absender-Impressum decided** — private address in Ludesch acceptable for a single batch. Formal business form (Kleinunternehmer) only required *before first paying customer*, not before sending letters.
- [ ] **Letter v1 reviewed** (`(C) Letter v1 — DE Trades.md` in this folder)

## After send

- Add columns to DB (or a separate CSV): `letter_sent_at`, `tracking_code`, `replied_at`, `reply_channel`.
- Wait 3–4 weeks for the response window (postal is slower than email — give it time).
- Review rate. Gate for Phase 2 was ≥ 3%. With n=8 that's ≥ 1 reply — noisy but a signal.
