# Letter v1 — DACH Trades (DE)

**Status:** Draft v1, awaiting Felix review.
**Target segment:** Vorarlberg Handwerker without a website.
**Channel:** Postal mail via print-API.
**Tracking:** Unique code per letter (VB01–VB08) in CTA URL.

---

## Design notes (read before editing the copy)

- **Formal Sie throughout.** Non-negotiable for this audience.
- **One page, no logo.** First version stays minimal — paper quality and a clean layout do more than graphic design for trust.
- **Handwritten signature scan** if possible. Huge trust signal for postal.
- **Font:** Serif (Georgia, Garamond, EB Garamond) at 11pt. Not Arial. Looks less like spam.
- **Length:** fits on one A4 page with room to breathe. Resist adding paragraphs.
- **No bullet lists inside the letter** — prose only. Bullets read as "marketing pamphlet."
- **Placeholders:** `{{...}}` get filled at mail-merge time.

---

## Letter body (copy into print-API template)

```
{{ABSENDER_BLOCK}}


{{EMPFAENGER_BLOCK}}


{{DATUM}}


Betreff: Eine Website für {{FIRMA}}


Sehr geehrte Damen und Herren,

wer heute in {{REGION}} einen {{KATEGORIE_LAIE}} sucht, googelt. Wer online
nicht zu finden ist, wird nicht angerufen — auch wenn die Arbeit besser
ist als die der Konkurrenz.

Mir ist aufgefallen, dass {{FIRMA}} keine eigene Website hat. Das ist der
Grund für diesen Brief.

Ich baue Websites für Handwerksbetriebe in Vorarlberg. Festpreis
590 Euro für den Standardumfang — einmalig, alles inklusive. In der
Regel fertig in 72 Stunden, komplett auf Deutsch, auf dem Handy gut
lesbar, mit Ihren Leistungen, Referenzbildern und Kontaktdaten. Hosting
und Domain im ersten Jahr inklusive. Von Ihrer Seite brauche ich nur
ein kurzes Gespräch und ein paar Fotos.

Bei Sonderwünschen — zusätzliche Unterseiten, Online-Anfrageformular,
Mehrsprachigkeit — rechnen wir den Mehraufwand transparent und vorab
dazu. Nichts ohne Ihre Freigabe.

Ich bin Softwareentwickler-Lehrling aus Vorarlberg und mache das
nebenberuflich. Daher der Preis — ich arbeite ohne Agentur-Overhead.

Wenn Sie sehen möchten, wie eine Website für {{FIRMA}} aussehen könnte,
schauen Sie auf folgender Seite vorbei:

    {{TRACKING_URL}}

Dort tragen Sie nur Firma, Telefonnummer und zwei Sätze zu Ihrem Betrieb
ein. Innerhalb von 24 Stunden melde ich mich mit einem ersten Entwurf
zurück. Unverbindlich, ohne versteckte Kosten, ohne Vertrag.

Mit freundlichen Grüßen


{{UNTERSCHRIFT}}

Felix Gmeiner
{{ABSENDER_EMAIL}}  |  {{ABSENDER_TELEFON}}
```

---

## Mail-merge variables

| Variable | Source | Example |
|---|---|---|
| `{{ABSENDER_BLOCK}}` | Static | Felix Gmeiner\nDorfstraße 41\n6713 Ludesch |
| `{{EMPFAENGER_BLOCK}}` | DB (`name`, `address`, `postal_code`, city) | Benzer Schlosserei-Metallbau\nRadetzkystraße 66\n6845 Hohenems |
| `{{ORT}}` | unused (removed) | — |
| `{{DATUM}}` | Send day | 28.04.2026 |
| `{{FIRMA}}` | DB `name` | Tischlerei Brändle |
| `{{REGION}}` | Static | Vorarlberg |
| `{{KATEGORIE_LAIE}}` | Map from `category` | Tischler / Elektriker / Installateur / Maler / Schlosser |
| `{{TRACKING_URL}}` | Domain + code | handwerkerweb.at/VB02 |
| `{{UNTERSCHRIFT}}` | PNG-Scan | — |

### `KATEGORIE_LAIE` mapping (laienverständlich, kein OSM-Jargon)

| OSM `category` | → Letter text |
|---|---|
| `carpenter` | Tischler |
| `electrician` | Elektriker |
| `plumber` | Installateur |
| `painter` | Maler |
| `locksmith` | Schlosser |
| `metal_construction` | Metallbauer |
| `roofer` | Dachdecker |
| `heating_engineer` | Heizungsbauer |
| _fallback_ | Handwerker |

---

## Worked example — Letter #2 (Tischlerei Brändle)

```
Felix Gmeiner
Dorfstraße 41
6713 Ludesch


Tischlerei Brändle
Achstraße 45
6844 Altach


28.04.2026


Betreff: Eine Website für Tischlerei Brändle


Sehr geehrte Damen und Herren,

wer heute in Vorarlberg einen Tischler sucht, googelt. Wer online
nicht zu finden ist, wird nicht angerufen — auch wenn die Arbeit besser
ist als die der Konkurrenz.

Mir ist aufgefallen, dass Tischlerei Brändle keine eigene Website hat.
Das ist der Grund für diesen Brief.

Ich baue Websites für Handwerksbetriebe in Vorarlberg. Festpreis
590 Euro für den Standardumfang — einmalig, alles inklusive. In der
Regel fertig in 72 Stunden, komplett auf Deutsch, auf dem Handy gut
lesbar, mit Ihren Leistungen, Referenzbildern und Kontaktdaten. Hosting
und Domain im ersten Jahr inklusive. Von Ihrer Seite brauche ich nur
ein kurzes Gespräch und ein paar Fotos.

Bei Sonderwünschen — zusätzliche Unterseiten, Online-Anfrageformular,
Mehrsprachigkeit — rechnen wir den Mehraufwand transparent und vorab
dazu. Nichts ohne Ihre Freigabe.

Ich bin Softwareentwickler-Lehrling aus Vorarlberg und mache das
nebenberuflich. Daher der Preis — ich arbeite ohne Agentur-Overhead.

Wenn Sie sehen möchten, wie eine Website für Tischlerei Brändle
aussehen könnte, schauen Sie auf folgender Seite vorbei:

    handwerkerweb.at/VB02

Dort tragen Sie nur Firma, Telefonnummer und zwei Sätze zu Ihrem Betrieb
ein. Innerhalb von 24 Stunden melde ich mich mit einem ersten Entwurf
zurück. Unverbindlich, ohne versteckte Kosten, ohne Vertrag.

Mit freundlichen Grüßen


[Unterschrift]

Felix Gmeiner
felix.gmeiner18@gmail.com  |  [Telefon]
```

---

## What I'm less sure about (flag these if you want to change them)

1. **€490 price in the letter** — strong CTA-filter but commits us to a price before we know if it's right. Alternative: "ab 490 Euro" (leaves upsell room but weakens signal).
2. **"Lehrling" disclosure** — I think it's the right move, but if you want to test the other version (just "Softwareentwickler aus Ludesch"), we can A/B split 4/4 on batch 1.
3. **"72 Stunden" delivery promise** — concrete and honest only if we actually can. Strategy doc has this as the fulfillment SLA — realistic given the existing Claude-based generator.
4. **No phone number as CTA** — cleanest for tracking, but trades people often prefer calling. If we add a phone CTA too, we lose attribution for phone replies unless we use a unique "mention code VBxx" line.

## Open items before we can mail

- Buy tracking domain (`handwerkerweb.at` — picked 2026-05-03, in cart at world4you)
- Stand up a minimal landing page (Cloudflare Pages: static HTML + form → logs visits + submissions)
- Pick print-API and upload this letter as a template
- Resolve Absender street address (full Impressum-valid line)
- Optional: handwritten-signature scan
