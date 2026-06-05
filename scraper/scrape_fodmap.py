#!/usr/bin/env python3
"""
Scraper for lav-FODMAP-oppskrifter fra utvalgte nettsider.

Kilder:
  lavfodmap        lavfodmap.no            (norsk, WordPress)
  lyngstad         lyngstadernaering.no    (norsk, WordPress)
  magevennligmat   magevennligmat.no       (norsk, Squarespace)
  fodmapeveryday   fodmapeveryday.com      (engelsk, JSON-LD)
  funwithoutfodmaps funwithoutfodmaps.com  (engelsk, JSON-LD)
  karlijns         karlijnskitchen.com     (engelsk, JSON-LD, 300+ middager)
  alittlebityummy  alittlebityummy.com     (engelsk, ernæringsfysiolog-godkjent)

Bruk:
  pip install requests beautifulsoup4
  python3 scrape_fodmap.py --sources lavfodmap lyngstad --limit 10
  python3 scrape_fodmap.py                # alle kilder, alt
  python3 scrape_fodmap.py --out ../data/oppskrifter.json

Output: JSON-array med felles skjema per oppskrift:
  id, title, source, url, language, categories, image, description,
  ingredients[], instructions[], servings, prep_time, cook_time, scraped_at
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
}
DELAY = 1.5  # sekunder mellom forespørsler – vær høflig
TIMEOUT = 20

session = requests.Session()
session.headers.update(HEADERS)
_last_request = [0.0]


def fetch(url, as_json=False):
    """Hent en URL med rate-limiting. Returnerer tekst/JSON eller None."""
    wait = DELAY - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.time()
    try:
        r = session.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json() if as_json else r.text
    except Exception as e:
        print(f"  ! Feil ved henting av {url}: {e}", file=sys.stderr)
        return None


def make_id(url):
    return hashlib.md5(url.encode()).hexdigest()[:12]


def clean(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def recipe_skeleton(url, source, language):
    return {
        "id": make_id(url),
        "title": None,
        "source": source,
        "url": url,
        "language": language,
        "categories": [],
        "image": None,
        "description": None,
        "ingredients": [],
        "instructions": [],
        "servings": None,
        "prep_time": None,
        "cook_time": None,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Generisk JSON-LD-parser (schema.org/Recipe) – brukes av engelske kilder
# ---------------------------------------------------------------------------

def find_jsonld_recipe(soup):
    """Finn et schema.org/Recipe-objekt i ld+json-blokker."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = []
        if isinstance(data, dict):
            candidates = data.get("@graph", [data])
        elif isinstance(data, list):
            candidates = data
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if "Recipe" in types:
                return obj
    return None


def parse_jsonld_recipe(obj, rec):
    rec["title"] = clean(obj.get("name"))
    rec["description"] = clean(obj.get("description")) or None
    img = obj.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, dict):
        img = img.get("url")
    rec["image"] = img
    rec["ingredients"] = [clean(i) for i in obj.get("recipeIngredient", []) if clean(i)]
    instructions = obj.get("recipeInstructions", [])
    steps = []
    if isinstance(instructions, str):
        steps = [clean(instructions)]
    else:
        for step in instructions:
            if isinstance(step, str):
                steps.append(clean(step))
            elif isinstance(step, dict):
                if step.get("@type") == "HowToSection":
                    for sub in step.get("itemListElement", []):
                        if isinstance(sub, dict):
                            steps.append(clean(sub.get("text", "")))
                else:
                    steps.append(clean(step.get("text", "")))
    rec["instructions"] = [s for s in steps if s]
    rec["servings"] = clean(str(obj.get("recipeYield", ""))) or None
    rec["prep_time"] = obj.get("prepTime")
    rec["cook_time"] = obj.get("cookTime")
    cats = obj.get("recipeCategory", [])
    if isinstance(cats, str):
        cats = [cats]
    rec["categories"] = [clean(c) for c in cats if clean(c)]
    return rec


def scrape_jsonld_site(name, sitemap_urls, url_filter, language, limit):
    """Generisk scraper: finn oppskrifts-URL-er via sitemap, parse JSON-LD."""
    urls = []
    for sm in sitemap_urls:
        xml = fetch(sm)
        if not xml:
            continue
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
        # sitemap-index → følg under-sitemaps som ser relevante ut
        subs = [u for u in locs if u.endswith(".xml")]
        pages = [u for u in locs if not u.endswith(".xml")]
        for sub in subs:
            sub_xml = fetch(sub)
            if sub_xml:
                pages += re.findall(r"<loc>(.*?)</loc>", sub_xml)
        urls += [u for u in pages if url_filter(u)]
        if urls:
            break
    urls = list(dict.fromkeys(urls))
    if limit:
        urls = urls[:limit]
    print(f"[{name}] {len(urls)} oppskrifts-URL-er funnet")

    recipes = []
    for i, url in enumerate(urls, 1):
        html = fetch(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        obj = find_jsonld_recipe(soup)
        if not obj:
            print(f"  - hopper over (ingen Recipe-skjema): {url}", file=sys.stderr)
            continue
        rec = parse_jsonld_recipe(obj, recipe_skeleton(url, name, language))
        if rec["title"] and rec["ingredients"]:
            recipes.append(rec)
            print(f"  [{i}/{len(urls)}] {rec['title']}")
    return recipes


# ---------------------------------------------------------------------------
# lavfodmap.no – WordPress, fritekst-oppskrifter med faste overskrifter
# ---------------------------------------------------------------------------

STEP_PREFIX = re.compile(r"^(slik gjør du|slik gjør|fremgangsmåte|tilberedning)\b[:\s]*", re.I)
ING_PREFIX = re.compile(r"^(ingredienser|dette trenger du)\b[:\s]*", re.I)
ING_HEADING = re.compile(r"(ingrediens|dette trenger du|^oppskrift)", re.I)
JUNK_LINE = re.compile(
    r"^(lagre$|prøv også|lag også|les også|les mer|håper det smaker|"
    r"julianne\b|relatert$|del |nb!|tips:)", re.I,
)


def parse_norwegian_blogpost(html, url, source):
    """Parser for norske WP-blogger: tittel, bilde, kategorier + seksjoner
    basert på overskrifter/fete avsnitt som 'Ingredienser' og 'Fremgangsmåte'."""
    soup = BeautifulSoup(html, "html.parser")
    rec = recipe_skeleton(url, source, "nb")

    h1 = soup.find("h1")
    rec["title"] = clean(h1.get_text()) if h1 else None
    og_img = soup.find("meta", property="og:image")
    rec["image"] = og_img["content"] if og_img and og_img.get("content") else None
    og_desc = soup.find("meta", property="og:description")
    rec["description"] = clean(og_desc["content"]) if og_desc and og_desc.get("content") else None

    # kategorier fra lenker til /tema/ (lavfodmap.no) eller /category/ (lyngstad)
    cats = set()
    for a in soup.find_all("a", href=re.compile(r"/(tema|category)/")):
        txt = clean(a.get_text())
        if txt and len(txt) < 40 and not txt.lower().startswith("les mer"):
            cats.add(txt)
    rec["categories"] = sorted(cats)

    # Finn innholdscontainer
    content = soup.find("div", class_=re.compile(r"(entry-content|et_pb_post_content|post-content)")) or soup

    # Del innholdet i seksjoner. Ny seksjon ved hver h2-h4, og ved linjer som
    # begynner med «Ingredienser» / «Slik gjør du» (Lyngstad har overskriften
    # som fet tekst, ofte i samme avsnitt som innholdet).
    sections = [{"head": None, "lines": []}]
    for el in content.find_all(["h2", "h3", "h4", "p", "li"]):
        if el.find_parent(["li", "p"]) is not None:
            continue  # unngå dobbeltbehandling av nøstede elementer
        for br in el.find_all("br"):
            br.replace_with("\n")
        lines = [clean(l) for l in el.get_text().split("\n") if clean(l)]
        if not lines:
            continue
        if el.name in ("h2", "h3", "h4"):
            sections.append({"head": lines[0], "lines": []})
            continue
        for line in lines:
            m = STEP_PREFIX.match(line) or ING_PREFIX.match(line)
            if m:
                sections.append({"head": m.group(1), "lines": []})
                rest = clean(line[m.end():])
                if rest:
                    sections[-1]["lines"].append(rest)
            elif not JUNK_LINE.match(line):
                sections[-1]["lines"].append(line)

    # Klassifiser seksjonene
    step_idx = []
    for i, sec in enumerate(sections):
        head = sec["head"] or ""
        if STEP_PREFIX.match(head):
            rec["instructions"] += sec["lines"]
            step_idx.append(i)
        elif ING_HEADING.search(head):
            rec["ingredients"] += sec["lines"]

    # Fallback (typisk lavfodmap.no): ingrediensene står under en overskrift
    # med rettens navn rett før «Fremgangsmåte»-seksjonen.
    if not rec["ingredients"] and step_idx:
        prev = sections[step_idx[0] - 1] if step_idx[0] > 0 else None
        if prev and prev["lines"]:
            rec["ingredients"] = [l for l in prev["lines"] if len(l) < 90]

    # porsjoner, f.eks. "Oppskriften gir 24 pannekaker"
    m = re.search(r"(?:gir|nok til)\s+(?:ca\.?\s*)?(\d+\s*\w*)", soup.get_text(), re.I)
    if m:
        rec["servings"] = clean(m.group(1))

    # rydd: fjern duplikater, behold rekkefølge
    rec["ingredients"] = list(dict.fromkeys(rec["ingredients"]))
    rec["instructions"] = list(dict.fromkeys(rec["instructions"]))
    return rec


def wp_get_all_posts(base, extra_params=""):
    """Hent alle poster via WP REST API med paginering."""
    posts, page = [], 1
    while True:
        url = f"{base}/wp-json/wp/v2/posts?per_page=100&page={page}{extra_params}"
        data = fetch(url, as_json=True)
        if not data:
            break
        posts += data
        if len(data) < 100:
            break
        page += 1
    return posts


def scrape_lavfodmap(limit):
    base = "https://lavfodmap.no"
    # Finn taksonomi-ID for oppskrifter ("tema"-taksonomien)
    recipe_urls = []
    taxes = fetch(f"{base}/wp-json/wp/v2/taxonomies", as_json=True) or {}
    tema_rest = None
    for slug, t in taxes.items():
        if slug not in ("category", "post_tag"):
            tema_rest = t.get("rest_base", slug)
            break
    term_id = None
    if tema_rest:
        terms = fetch(f"{base}/wp-json/wp/v2/{tema_rest}?slug=lavfodmap-oppskrifter", as_json=True)
        if terms:
            term_id = terms[0]["id"]

    if term_id:
        posts, page = [], 1
        while True:
            data = fetch(
                f"{base}/wp-json/wp/v2/posts?per_page=100&page={page}&{tema_rest}={term_id}",
                as_json=True,
            )
            if not data:
                break
            posts += data
            if len(data) < 100:
                break
            page += 1
        recipe_urls = [p["link"] for p in posts]
    else:
        # Fallback: crawle arkivsider
        page = 1
        while True:
            suffix = "" if page == 1 else f"page/{page}/"
            html = fetch(f"{base}/tema/lavfodmap-oppskrifter/{suffix}")
            if not html:
                break
            links = set(re.findall(r'href="(https://lavfodmap\.no/[a-z0-9-]+/)"', html))
            links = {
                u for u in links
                if not re.search(r"/(tema|author|wp-content|page|dagbok|konsoll)", u)
            }
            if not links - set(recipe_urls):
                break
            recipe_urls += sorted(links - set(recipe_urls))
            page += 1

    recipe_urls = list(dict.fromkeys(recipe_urls))
    if limit:
        recipe_urls = recipe_urls[:limit]
    print(f"[lavfodmap] {len(recipe_urls)} oppskrifts-URL-er funnet")

    recipes = []
    for i, url in enumerate(recipe_urls, 1):
        html = fetch(url)
        if not html:
            continue
        rec = parse_norwegian_blogpost(html, url, "lavfodmap.no")
        if rec["title"] and (rec["ingredients"] or rec["instructions"]):
            recipes.append(rec)
            print(f"  [{i}/{len(recipe_urls)}] {rec['title']}")
        else:
            print(f"  - hopper over (fant ikke oppskriftsinnhold): {url}", file=sys.stderr)
    return recipes


# ---------------------------------------------------------------------------
# lyngstadernaering.no – WordPress
# ---------------------------------------------------------------------------

def scrape_lyngstad(limit):
    base = "https://lyngstadernaering.no"
    posts = wp_get_all_posts(base)
    recipe_urls = [p["link"] for p in posts if "lavfodmap" in p.get("slug", "")]
    if not recipe_urls:  # fallback: oversiktssiden
        html = fetch(f"{base}/lavfodmap-oppskrifter")
        if html:
            recipe_urls = list(dict.fromkeys(
                u for u in re.findall(r'href="(https://lyngstadernaering\.no/[a-z0-9-]+)"', html)
                if "lavfodmap" in u and "oppskrifter" not in u
            ))
    if limit:
        recipe_urls = recipe_urls[:limit]
    print(f"[lyngstad] {len(recipe_urls)} oppskrifts-URL-er funnet")

    recipes = []
    for i, url in enumerate(recipe_urls, 1):
        html = fetch(url)
        if not html:
            continue
        rec = parse_norwegian_blogpost(html, url, "lyngstadernaering.no")
        if rec["title"] and (rec["ingredients"] or rec["instructions"]):
            recipes.append(rec)
            print(f"  [{i}/{len(recipe_urls)}] {rec['title']}")
        else:
            print(f"  - hopper over (fant ikke oppskriftsinnhold): {url}", file=sys.stderr)
    return recipes


# ---------------------------------------------------------------------------
# magevennligmat.no – Squarespace (JSON-API: ?format=json)
# ---------------------------------------------------------------------------

def scrape_magevennligmat(limit):
    base = "https://www.magevennligmat.no"
    data = fetch(f"{base}/oppskrifter?format=json", as_json=True)
    items = (data or {}).get("items", [])
    if not items:
        # Squarespace legger ofte innhold i undersamlinger – prøv hovedsiden
        data = fetch(f"{base}/?format=json", as_json=True) or {}
        for c in data.get("collections", []):
            if "oppskrift" in (c.get("urlId") or ""):
                sub = fetch(f"{base}/{c['urlId']}?format=json", as_json=True) or {}
                items += sub.get("items", [])
    if not items:
        print("[magevennligmat] Fikk ikke data – siden ser ut til å blokkere "
              "automatiserte kall. Hopper over.", file=sys.stderr)
        return []
    if limit:
        items = items[:limit]
    print(f"[magevennligmat] {len(items)} elementer funnet")

    recipes = []
    for item in items:
        url = urljoin(base, item.get("fullUrl", ""))
        rec = recipe_skeleton(url, "magevennligmat.no", "nb")
        rec["title"] = clean(item.get("title"))
        rec["image"] = item.get("assetUrl")
        rec["categories"] = item.get("categories", [])
        body = BeautifulSoup(item.get("body", ""), "html.parser")
        parsed = parse_norwegian_blogpost(str(body), url, "magevennligmat.no")
        rec["ingredients"] = parsed["ingredients"]
        rec["instructions"] = parsed["instructions"]
        rec["description"] = clean(item.get("excerpt", "")) or None
        if rec["title"] and (rec["ingredients"] or rec["instructions"]):
            recipes.append(rec)
            print(f"  - {rec['title']}")
    return recipes


# ---------------------------------------------------------------------------
# karlijnskitchen.com – WordPress + Tasty Recipes (JSON-LD), kategori-crawl
# ---------------------------------------------------------------------------

KARLIJNS_KATEGORIER = [
    "dinner", "lunch-recipes", "breakfast", "healthy-snacks",
    "desserts", "baking", "snack", "spreads-condiments", "fast-and-easy",
]

def scrape_karlijns(limit):
    base = "https://www.karlijnskitchen.com/en/recipes/"
    urls = []
    for cat in KARLIJNS_KATEGORIER:
        page = 1
        while True:
            u = f"{base}{cat}/" + ("" if page == 1 else f"page/{page}/")
            html = fetch(u)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            # Oppskriftslenker i listingen har title-attributt; nav-lenker har ikke
            nye = []
            for a in soup.find_all("a", title=True, href=re.compile(
                    r"^https://www\.karlijnskitchen\.com/en/[a-z0-9-]+/$")):
                href = a["href"]
                if "/recipes/" not in href and "/tag/" not in href and href not in urls:
                    nye.append(href)
            if not nye:
                break
            urls += nye
            page += 1
        if limit and len(urls) >= limit:
            break
    urls = list(dict.fromkeys(urls))
    if limit:
        urls = urls[:limit]
    print(f"[karlijns] {len(urls)} kandidat-URL-er funnet")

    recipes = []
    for i, url in enumerate(urls, 1):
        html = fetch(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        obj = find_jsonld_recipe(soup)
        if not obj:
            continue  # ikke en oppskriftsside (f.eks. tipsartikkel)
        rec = parse_jsonld_recipe(obj, recipe_skeleton(url, "karlijnskitchen.com", "en"))
        if rec["title"] and rec["ingredients"]:
            recipes.append(rec)
            print(f"  [{i}/{len(urls)}] {rec['title']}")
    return recipes


# ---------------------------------------------------------------------------
# alittlebityummy.com – Recipe-skjema uten ingredienser; ingrediensene ligger
# i data-attributter i HTML (med både amerikanske og metriske mengder)
# ---------------------------------------------------------------------------

def scrape_alittlebityummy(limit):
    xml = fetch("https://alittlebityummy.com/recipes-sitemap.xml")
    urls = [u for u in re.findall(r"<loc>(.*?)</loc>", xml or "")
            if "/recipe/en-us/" in u]
    urls = list(dict.fromkeys(urls))
    if limit:
        urls = urls[:limit]
    print(f"[alittlebityummy] {len(urls)} oppskrifts-URL-er funnet")

    recipes = []
    for i, url in enumerate(urls, 1):
        html = fetch(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        rec = recipe_skeleton(url, "alittlebityummy.com", "en")

        obj = find_jsonld_recipe(soup)
        if obj:
            rec = parse_jsonld_recipe(obj, rec)

        # Ingredienser fra HTML – foretrekk metriske mengder (secondary)
        ingredienser = []
        for b in soup.find_all("b", class_="ingredient-unit-display"):
            amt = b.get("data-secondary-amount") or b.get("data-primary-amount") or ""
            unit = b.get("data-secondary-unit") or b.get("data-primary-unit") or ""
            navn_el = b.find_next("span", class_="ingredient-name-display")
            navn = (navn_el.get("data-standard") if navn_el else "") or \
                   (clean(navn_el.get_text()) if navn_el else "")
            linje = clean(" ".join(x for x in (amt, unit, navn) if x))
            if linje:
                ingredienser.append(linje)
        rec["ingredients"] = list(dict.fromkeys(ingredienser))

        # Fremgangsmåte: fall tilbake til "Method"-listen i HTML om nødvendig
        if not rec["instructions"]:
            metode = soup.find(["h2", "h3"], string=re.compile(r"^\s*Method\s*$", re.I))
            ol = metode.find_next("ol") if metode else None
            if ol:
                rec["instructions"] = [clean(li.get_text()) for li in ol.find_all("li") if clean(li.get_text())]

        # Kategorier fra "FEATURED IN"-lenkene
        if not rec["categories"]:
            rec["categories"] = sorted({clean(a.get_text())
                for a in soup.find_all("a", href=re.compile(r"/recipe/recipe_category/"))
                if clean(a.get_text())})

        if not rec["title"]:
            h1 = soup.find("h1")
            rec["title"] = clean(h1.get_text()) if h1 else None

        if rec["title"] and rec["ingredients"] and rec["instructions"]:
            recipes.append(rec)
            print(f"  [{i}/{len(urls)}] {rec['title']}")
        else:
            print(f"  - hopper over (mangler {'ingredienser' if not rec['ingredients'] else 'fremgangsmåte'}): {url}",
                  file=sys.stderr)
    return recipes


# ---------------------------------------------------------------------------

SOURCES = {
    "karlijns": scrape_karlijns,
    "alittlebityummy": scrape_alittlebityummy,
    "lavfodmap": scrape_lavfodmap,
    "lyngstad": scrape_lyngstad,
    "magevennligmat": scrape_magevennligmat,
    "fodmapeveryday": lambda limit: scrape_jsonld_site(
        "fodmapeveryday.com",
        ["https://www.fodmapeveryday.com/sitemap_index.xml",
         "https://www.fodmapeveryday.com/wp-sitemap.xml"],
        lambda u: "/recipes/" in u and urlparse(u).path.strip("/").count("/") >= 1,
        "en",
        limit,
    ),
    "funwithoutfodmaps": lambda limit: scrape_jsonld_site(
        "funwithoutfodmaps.com",
        ["https://funwithoutfodmaps.com/sitemap_index.xml",
         "https://funwithoutfodmaps.com/wp-sitemap.xml"],
        lambda u: re.search(r"funwithoutfodmaps\.com/[a-z0-9-]+/$", u) is not None,
        "en",
        limit,
    ),
}


def main():
    ap = argparse.ArgumentParser(description="Scrape lav-FODMAP-oppskrifter til JSON")
    ap.add_argument("--sources", nargs="+", choices=SOURCES.keys(),
                    default=list(SOURCES.keys()), help="Kilder som skal scrapes")
    ap.add_argument("--limit", type=int, default=None,
                    help="Maks antall oppskrifter per kilde (til testing)")
    ap.add_argument("--out", default="oppskrifter.json", help="Output-fil")
    args = ap.parse_args()

    all_recipes = []
    for src in args.sources:
        print(f"\n=== {src} ===")
        try:
            all_recipes += SOURCES[src](args.limit)
        except KeyboardInterrupt:
            print("\nAvbrutt – lagrer det som er hentet så langt.")
            break
        except Exception as e:
            print(f"[{src}] feilet: {e}", file=sys.stderr)

    # dedup på URL
    seen, unique = set(), []
    for r in all_recipes:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    # JS-variant slik at web-appen kan åpnes rett fra disk (uten lokal server)
    js_out = re.sub(r"\.json$", "", args.out) + ".js"
    with open(js_out, "w", encoding="utf-8") as f:
        f.write("window.RECIPES = ")
        json.dump(unique, f, ensure_ascii=False)
        f.write(";\n")
    print(f"\n✓ {len(unique)} oppskrifter lagret i {args.out} og {js_out}")


if __name__ == "__main__":
    main()
