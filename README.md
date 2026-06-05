# FODMAP-oppskriftsscraper

Henter lav-FODMAP-oppskrifter fra fem nettsider og lagrer dem som JSON til bruk i web-appen.

## Oppsett

```bash
pip3 install requests beautifulsoup4
```

## Bruk

```bash
# Test først med få oppskrifter per kilde:
python3 scrape_fodmap.py --limit 5

# Bare norske kilder:
python3 scrape_fodmap.py --sources lavfodmap lyngstad magevennligmat

# Alt, til valgfri fil:
python3 scrape_fodmap.py --out ../data/oppskrifter.json
```

Kilder: `lavfodmap` (lavfodmap.no), `lyngstad` (lyngstadernaering.no), `magevennligmat` (magevennligmat.no, blokkerer p.t. – hoppes over), `fodmapeveryday` (fodmapeveryday.com), `funwithoutfodmaps` (funwithoutfodmaps.com), `karlijns` (karlijnskitchen.com, 300+ middager), `alittlebityummy` (alittlebityummy.com, ernæringsfysiolog-godkjent).

## JSON-skjema

```json
{
  "id": "a1b2c3d4e5f6",
  "title": "Bananpannekaker",
  "source": "lyngstadernaering.no",
  "url": "https://...",
  "language": "nb",
  "categories": ["Frokost"],
  "image": "https://...",
  "description": "...",
  "ingredients": ["3 egg", "..."],
  "instructions": ["Ha alle ingrediensene...", "..."],
  "servings": "24 pannekaker",
  "prep_time": null,
  "cook_time": null,
  "scraped_at": "2026-06-05T12:00:00+00:00"
}
```

## Merknader

- Scriptet venter 1,5 s mellom forespørsler for å være høflig mot sidene.
- De norske bloggene har oppskrifter i fritekst; parseren ser etter «Ingredienser» / «Slik gjør du» / «Fremgangsmåte». Noen oppskrifter med avvikende format kan hoppes over (logges til stderr).
- De engelske sidene har strukturert Recipe-data (JSON-LD) og gir mest komplette resultater.
- Kun til personlig bruk – tekst og bilder er opphavsrettsbeskyttet.
