#!/usr/bin/env python3
"""
Etterbehandler oppskrifter.json:
  1. Konverterer amerikanske enheter til metrisk (cups→dl, oz→g, lb→g,
     °F→°C, inches→cm, tbsp→ss, tsp→ts). Basert på 1 cup = 250 ml,
     1 ss = 15 ml = 3 ts (jf. langbein.com/conversions).
  2. Harmoniserer kategoriene til et lite norsk sett.
  3. Gjør ISO-tider (PT10M) om til lesbar form (10 min).

Kjøres uten argumenter: python3 etterbehandle.py
Skriver oppskrifter.json og oppskrifter.js på nytt.
"""

import json
import re

FRAK = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1/3, "⅔": 2/3, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}

def til_tall(s):
    """'1 1/2', '1/2', '½', '1.5', '1,5' → float"""
    s = s.strip()
    if s in FRAK:
        return FRAK[s]
    if len(s) > 1 and s[-1] in FRAK:
        return float(s[:-1].strip() or 0) + FRAK[s[-1]]
    m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.match(r"^(\d+)/(\d+)$", s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    return float(s.replace(",", "."))

def norsk(x, desimaler=1):
    """Tall → norsk format med vanlig avrunding: 2.5 → '2,5', 3.0 → '3'"""
    f = 10 ** desimaler
    avr = int(x * f + 0.5) / f
    if avr == int(avr):
        return str(int(avr))
    return f"{avr:.{desimaler}f}".replace(".", ",")

def rund(x, naermeste):
    return max(naermeste, round(x / naermeste) * naermeste)

# Tallmønster: heltall, desimal, brøk (1/2, 1 1/2) eller unicode-brøk
TALL = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d*[.,]\d+|\d+|[¼½¾⅓⅔⅛⅜⅝⅞]|\d+\s*[¼½¾⅓⅔⅛])"

def _konv_mengde(m, faktor, enhet, avrunding=None, desimaler=1):
    """Konverter ett (ev. område-)treff: '1-2 cups' → '2,5-5 dl'"""
    a = til_tall(m.group(1)) * faktor
    if avrunding:
        a = rund(a, avrunding)
    res = norsk(a, desimaler)
    if m.group(2):
        b = til_tall(m.group(2)) * faktor
        if avrunding:
            b = rund(b, avrunding)
        res += "–" + norsk(b, desimaler)
    return f"{res} {enhet}"

def _re(enheter):
    # tillater "9-inch" og "9 inch"; valgfritt område som "1-2 cups"
    return re.compile(rf"({TALL})\s*(?:[-–—]\s*({TALL})\s*)?[-\s]*(?:{enheter})(?![a-z])", re.I)

RE_CUP   = _re(r"cups?")
RE_FLOZ  = _re(r"fl\.?\s*oz\.?|fluid ounces?")
RE_OZ    = _re(r"oz\.?|ounces?")
RE_LB    = _re(r"lbs?\.?|pounds?")
RE_TBSP  = _re(r"tbsps?\.?|tablespoons?")
RE_TSP   = _re(r"tsps?\.?|teaspoons?")
RE_INCH  = _re(r"inch(?:es)?|″")
RE_F     = re.compile(r"(\d{2,3})\s*(?:°|degrees?\s*)?F(?:ahrenheit)?\b", re.I)
RE_PINT  = _re(r"pints?")
RE_QUART = _re(r"quarts?|qt\.?")
RE_STICK = re.compile(rf"({TALL})\s*sticks?\s+(?:of\s+)?butter", re.I)
RE_PARENTES = re.compile(
    r"\s*\((?:[^()]*\b(?:cups?|oz|ounces?|lbs?|pounds?|inch(?:es)?|fl\.?\s*oz)\b[^()]*)\)", re.I)

def konverter_tekst(t):
    """Konverter alle imperiale enheter i en tekststreng til metrisk."""
    if not t:
        return t
    # Fjern parentes-dubletter som "(2 cups)" når metrisk finnes fra før
    if re.match(rf"^\s*{TALL}\s*(g|kg|ml|dl|l)\b", t):
        t = RE_PARENTES.sub("", t)
    t = RE_F.sub(lambda m: f"{rund((int(m.group(1)) - 32) * 5 / 9, 5):d} °C"
                 if int(m.group(1)) >= 90 else m.group(0), t)
    t = RE_FLOZ.sub(lambda m: _konv_mengde(m, 30, "ml", avrunding=5, desimaler=0), t)
    t = RE_CUP.sub(lambda m: _konv_mengde(m, 2.5, "dl"), t)
    t = RE_OZ.sub(lambda m: _konv_mengde(m, 28.35, "g", avrunding=5, desimaler=0), t)
    t = RE_LB.sub(lambda m: _konv_mengde(m, 453.6, "g", avrunding=10, desimaler=0), t)
    t = RE_PINT.sub(lambda m: _konv_mengde(m, 4.73, "dl"), t)
    t = RE_QUART.sub(lambda m: _konv_mengde(m, 0.95, "l"), t)
    t = RE_TBSP.sub(lambda m: _konv_mengde(m, 1, "ss"), t)
    t = RE_TSP.sub(lambda m: _konv_mengde(m, 1, "ts"), t)
    t = RE_INCH.sub(lambda m: _konv_mengde(m, 2.54, "cm", avrunding=0.5), t)
    t = RE_STICK.sub(lambda m: f"{rund(til_tall(m.group(1)) * 113, 5):d} g butter", t)
    return t

RE_ISO_TID = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

def lesbar_tid(t):
    if not t:
        return t
    m = RE_ISO_TID.match(str(t).strip())
    if not m:
        return t
    timer, minutter = int(m.group(1) or 0), int(m.group(2) or 0)
    deler = []
    if timer:
        deler.append(f"{timer} t")
    if minutter:
        deler.append(f"{minutter} min")
    return " ".join(deler) or t

# ---------------------------------------------------------------------------
# Kategorier → lite norsk sett
# ---------------------------------------------------------------------------

KATEGORI_MAP = {
    # Frokost
    "breakfast": "Frokost", "frokost": "Frokost", "brunch": "Frokost",
    "frokost og lunsj": ("Frokost", "Lunsj"), "smoothie bowl": "Frokost",
    "eggs": "Frokost", "break": "Frokost",
    # Lunsj
    "lunch": "Lunsj", "lunsj": "Lunsj", "sandwich": "Lunsj",
    # Middag
    "dinner": "Middag", "middag": "Middag", "main course": "Middag",
    "main dish": "Middag", "diner": "Middag", "entree": "Middag",
    "casserole": "Middag", "soup": "Middag", "bbq": "Middag",
    "bowl": "Middag", "chicken": "Middag", "pasta": "Middag",
    "lunsj/middag": ("Lunsj", "Middag"), "dinner & lunch": ("Lunsj", "Middag"),
    "lunch or dinner": ("Lunsj", "Middag"), "lunch & dinner": ("Lunsj", "Middag"),
    # Dessert og søtt
    "dessert": "Dessert og søtt", "desserts": "Dessert og søtt",
    "desserter og kaker": "Dessert og søtt", "treat": "Dessert og søtt",
    "treats": "Dessert og søtt", "sweets": "Dessert og søtt",
    "cake": "Dessert og søtt", "cookies": "Dessert og søtt",
    "candy": "Dessert og søtt", "ice cream": "Dessert og søtt",
    "pastry": "Dessert og søtt", "muffins": "Dessert og søtt",
    "kos": "Dessert og søtt", "cakes & sweets": "Dessert og søtt",
    "dessert/snacks": ("Dessert og søtt", "Snacks og forretter"),
    # Bakst
    "baking": "Bakst", "bakst": "Bakst", "bread": "Bakst", "bakken": "Bakst",
    "glutenfri bakst": "Bakst", "surdeig": "Bakst", "surdeig av spelt": "Bakst",
    # Snacks og forretter
    "snack": "Snacks og forretter", "snacks": "Snacks og forretter",
    "snacks og lette måltid": "Snacks og forretter",
    "appetizer": "Snacks og forretter", "starter": "Snacks og forretter",
    "party snack": "Snacks og forretter", "party snacks": "Snacks og forretter",
    "healthy snack": "Snacks og forretter", "healthy snacks": "Snacks og forretter",
    "dip": "Snacks og forretter",
    # Tilbehør og salat
    "side dish": "Tilbehør og salat", "side dishes": "Tilbehør og salat",
    "tilbehør": "Tilbehør og salat", "salad": "Tilbehør og salat",
    # Saus og dressing
    "sauce": "Saus og dressing", "condiment": "Saus og dressing",
    "condiments": "Saus og dressing", "dressing": "Saus og dressing",
    "salsa": "Saus og dressing", "seasoning": "Saus og dressing",
    "spread": "Saus og dressing", "spreads & sauces": "Saus og dressing",
    "sauser og dressinger": "Saus og dressing",
    "sauzes and condiments": "Saus og dressing",
    "sauces and spreads": "Saus og dressing",
    "spreads and sauces": "Saus og dressing",
    "sauces and dressings": "Saus og dressing",
    # Drikke
    "beverage": "Drikke", "drinks": "Drikke", "drikke": "Drikke",
    # Jul og høytid
    "christmas": "Jul og høytid", "jul og julekaker": "Jul og høytid",
    "høytid": "Jul og høytid", "holiday": "Jul og høytid",
    # Vegetar
    "vegetarian options": "Vegetar", "vegetarian": "Vegetar", "vegan": "Vegetar",
    # Grunnoppskrifter
    "basic": "Grunnoppskrifter",
}
# Kategorier uten matfaglig verdi droppes
DROPP = {
    "lavfodmap oppskrifter", "lavfodmap-hjelp", "lavfodmap tips", "tips",
    "nasjonalitet", "hverdagen", "lavfodmap på reise",
    "mine reisetips og erfaringer", "lav fodmap-dietten", "høst",
    "italian", "recipes",
}

def harmoniser_kategorier(kategorier):
    nye = []
    for k in kategorier:
        # splitt komma-lister som "lunch, dinner, vegetarian options"
        for del_ in re.split(r"\s*,\s*", k):
            nokkel = del_.strip().lower()
            if not nokkel or nokkel in DROPP:
                continue
            res = KATEGORI_MAP.get(nokkel)
            if res is None:
                continue  # ukjent → dropp heller enn å forsøple settet
            if isinstance(res, tuple):
                nye += list(res)
            else:
                nye.append(res)
    return sorted(set(nye))


def main():
    with open("oppskrifter.json", encoding="utf-8") as f:
        data = json.load(f)

    for r in data:
        r["ingredients"] = [konverter_tekst(i) for i in r["ingredients"]]
        r["instructions"] = [konverter_tekst(s) for s in r["instructions"]]
        if r.get("servings"):
            r["servings"] = konverter_tekst(r["servings"])
        r["prep_time"] = lesbar_tid(r.get("prep_time"))
        r["cook_time"] = lesbar_tid(r.get("cook_time"))
        r["categories"] = harmoniser_kategorier(r["categories"])

    with open("oppskrifter.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open("oppskrifter.js", "w", encoding="utf-8") as f:
        f.write("window.RECIPES = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")

    fra_kat = sorted({k for r in data for k in r["categories"]})
    print(f"✓ {len(data)} oppskrifter etterbehandlet")
    print("Kategorier nå:", ", ".join(fra_kat))


if __name__ == "__main__":
    main()
