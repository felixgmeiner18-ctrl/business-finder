# Absender (Sender) Details — Phase 1

> **Confirmed by Felix 2026-04-23.** Used in every outbound letter's Absender-Block (top of letter + envelope return address).

## Postal Absender

```
Felix Gmeiner
Dorfstraße 41
6713 Ludesch
Österreich
```

## Contact line (bottom of letter body)

- Email: felix.gmeiner18@gmail.com
- Telefon: [TBD — add before first letter sends]

## Env vars (for generate-letters.py)

```
ABSENDER_NAME="Felix Gmeiner"
ABSENDER_STRASSE="Dorfstraße 41"
ABSENDER_PLZ_ORT="6713 Ludesch"
ABSENDER_LAND="Österreich"
ABSENDER_EMAIL="felix.gmeiner18@gmail.com"
ABSENDER_TELEFON=""   # fill when available
```

## Notes

- **PLZ 6713** = Ludesch (corrected from earlier draft that used 6710 — that was my mistake).
- Private-individual sender for Phase 1. No Impressum pflicht because this is outgoing B2B postal solicitation, not a website/commercial offering.
- When first paying customer signs → register Kleinunternehmer (AT) → update Absender to reflect business form (`Felix Gmeiner e.U.` or similar).
- Never printed on the envelope as "Softwareentwickler-Lehrling" — that designation only appears inside the letter body. Envelope Absender is name + postal address only.
