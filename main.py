from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from google import genai
from google.genai import types

from PIL import Image

import statistics
import traceback
import httpx
import base64
import json
import re
import os
import io

# ---------------------------------------------------
# APP
# ---------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# ENV
# ---------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")

print("GEMINI:", bool(GEMINI_API_KEY))
print("VISION:", bool(GOOGLE_VISION_API_KEY))

# ---------------------------------------------------
# GEMINI
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# DESIGN DETECTION
# ---------------------------------------------------

DESIGN_KEYWORDS = [
    "fritz hansen",
    "arne jacobsen",
    "wegner",
    "hans wegner",
    "hay",
    "mater",
    "eames",
    "kartell",
    "louis poulsen",
    "montana",
    "gubi",
    "børge mogensen",
    "ph lamp",
    "panthella",
    "series 7",
    "syver stol",
    "ant chair",
    "myren",
]

# ---------------------------------------------------
# SEARCH CLEANUP
# ---------------------------------------------------

COLORS = [
    "sort",
    "hvid",
    "grå",
    "grøn",
    "gul",
    "sennepsgul",
    "blå",
    "brun",
    "beige",
    "rød",
    "orange",
    "lilla",
    "pink",
    "sølv",
    "guld",
    "kobber",
]

REMOVE_WORDS = [
    "god stand",
    "flot stand",
    "brugt",
    "flot",
    "velholdt",
    "unik",
    "sjælden",
    "smuk",
    "patina",
    "næsten ny",
]

# ---------------------------------------------------
# SMART SEARCH ENRICHMENT
# ---------------------------------------------------

MATERIAL_WORDS = [
    "læder",
    "teak",
    "eg",
    "keramik",
    "glas",
    "messing",
    "marmor",
    "rattan",
]

CATEGORY_WORDS = [
    "sofa",
    "stol",
    "bord",
    "lampe",
    "vase",
    "reol",
    "lænestol",
    "spisebord",
    "pendel",
]

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok"}

# ---------------------------------------------------
# IMAGE OPTIMIZE
# ---------------------------------------------------

def optimize_image(image_bytes):

    image = Image.open(io.BytesIO(image_bytes))
    image = image.convert("RGB")

    image.thumbnail((1400, 1400))

    output = io.BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=72,
        optimize=True
    )

    optimized = output.getvalue()

    print("=" * 40)
    print(f"IMAGE: {len(image_bytes)} → {len(optimized)} bytes")
    print("=" * 40)

    return optimized

# ---------------------------------------------------
# SEARCH TERM OPTIMIZE
# ---------------------------------------------------

def optimize_search_term(search_term):

    original = search_term

    search_term = search_term.lower()

    replacements = {
        "formspændt stol": "spisebordsstol",
        "sofabænk": "sofa",
        "daybed": "sofa",
    }

    for old, new in replacements.items():
        search_term = search_term.replace(old, new)

    for color in COLORS:

        search_term = re.sub(
            rf"\b{color}\b",
            "",
            search_term,
            flags=re.IGNORECASE
        )

    for word in REMOVE_WORDS:

        search_term = re.sub(
            rf"\b{re.escape(word)}\b",
            "",
            search_term,
            flags=re.IGNORECASE
        )

    search_term = re.sub(
        r"\s+",
        " ",
        search_term
    ).strip()

    parts = search_term.split()

    if len(parts) > 3:
        search_term = " ".join(parts[:3])

    print("=" * 40)
    print("SEARCH OPTIMIZATION")
    print(f"ORIGINAL: {original}")
    print(f"OPTIMIZED: {search_term}")
    print("=" * 40)

    return search_term

# ---------------------------------------------------
# SMART SEARCH TERM
# ---------------------------------------------------

def build_smart_search_term(search_term):

    search_term = search_term.lower()

    words = search_term.split()

    category = None
    material = None

    for word in CATEGORY_WORDS:

        if word in words:
            category = word
            break

    for word in MATERIAL_WORDS:

        if word in words:
            material = word
            break

    if category and material:

        if material == "læder" and category == "sofa":
            final_term = "lædersofa"

        elif material == "keramik" and category == "lampe":
            final_term = "keramiklampe"

        else:
            final_term = f"{material} {category}"

    elif category:

        final_term = category

    else:

        final_term = search_term

    print("=" * 40)
    print("SMART SEARCH")
    print(f"INPUT: {search_term}")
    print(f"OUTPUT: {final_term}")
    print("=" * 40)

    return final_term

# ---------------------------------------------------
# GOOGLE VISION
# ---------------------------------------------------

async def detect_web_entities(image_bytes):

    try:

        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        url = (
            "https://vision.googleapis.com/v1/images:annotate"
            f"?key={GOOGLE_VISION_API_KEY}"
        )

        payload = {
            "requests": [
                {
                    "image": {
                        "content": base64_image
                    },
                    "features": [
                        {
                            "type": "WEB_DETECTION",
                            "maxResults": 10
                        }
                    ]
                }
            ]
        }

        async with httpx.AsyncClient(timeout=20) as http:

            response = await http.post(
                url,
                json=payload
            )

        data = response.json()

        entities = []

        try:

            web_entities = (
                data["responses"][0]
                ["webDetection"]
                ["webEntities"]
            )

            for entity in web_entities:

                desc = entity.get("description", "").strip()
                score = entity.get("score", 0)

                if score >= 0.70 and len(desc) > 2:

                    entities.append({
                        "name": desc,
                        "score": score
                    })

        except:
            pass

        print("WEB ENTITIES:", entities)

        return entities

    except Exception as e:

        print("VISION ERROR:", e)

        return []

# ---------------------------------------------------
# STRONG DESIGN MATCH
# ---------------------------------------------------

def extract_strong_design_match(web_entities):

    if not web_entities:
        return None

    best_match = None
    best_score = 0

    for entity in web_entities:

        name = entity.get("name", "").lower()
        score = entity.get("score", 0)

        for keyword in DESIGN_KEYWORDS:

            if keyword in name and score >= 0.80:

                if score > best_score:

                    best_match = name
                    best_score = score

    if best_match:

        print("=" * 40)
        print("STRONG DESIGN MATCH")
        print(best_match)
        print(best_score)
        print("=" * 40)

    return best_match

# ---------------------------------------------------
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(
    image_bytes,
    web_entities,
    strong_design_match=None
):

    design_hint = ""

    if strong_design_match:

        design_hint = f"""

Google Vision fandt sandsynligvis:
{strong_design_match}

Brug dette hvis objektet matcher visuelt.
"""

    prompt = f"""
Du analyserer brugte genstande i Danmark.

Google Vision entities:
{web_entities}

{design_hint}

VIGTIGT:

- Fokusér kun på hovedobjektet
- Ignorér baggrund
- Gæt ikke designer hvis usikker

Search_term skal ligne almindelige DBA søgninger.

Brug simple ord.

Brug IKKE:
- farver
- stand
- tekniske beskrivelser

Returnér KUN valid JSON:

{{
  "title": "Kort titel",
  "category": "Kategori",
  "condition": "Kort vurdering",
  "search_term": "Simpel DBA søgning"
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/jpeg"
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.1
        )
    )

    text = response.text.strip()

    text = re.sub(
        r"```json|```",
        "",
        text
    ).strip()

    print(text)

    return json.loads(text)

# ---------------------------------------------------
# DIRECT DBA SEARCH
# ---------------------------------------------------

async def dba_search(query):

    try:

        print("=" * 40)
        print(f"DBA SEARCH: {query}")
        print("=" * 40)

        query_words = query.lower().split()

        url = (
            "https://www.dba.dk/recommerce/forsale/search"
            f"?q={query}"
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=20) as http:

            response = await http.get(
                url,
                headers=headers
            )

        html = response.text

        print("=" * 40)
        print(f"HTML LENGTH: {len(html)}")
        print("=" * 40)

        # ---------------------------------------------------
        # TITLE + PRICE MATCHING
        # ---------------------------------------------------

        prices = []

        listing_pattern = re.findall(
            r'{"title":"(.*?)".*?"price":{"price":"(.*?)"',
            html
        )

        print(f"LISTINGS FOUND: {len(listing_pattern)}")

        for title, raw_price in listing_pattern:

            try:

                title_lower = title.lower()

                # REQUIRE ALL SEARCH WORDS
                valid = all(
                    word in title_lower
                    for word in query_words
                )

                if not valid:
                    continue

                raw_price = raw_price.replace(".", "")
                raw_price = raw_price.replace(",", "")

                price = int(raw_price)

                if 50 <= price <= 250000:

                    prices.append(price)

                    print(
                        f"VALID: {title} → {price}"
                    )

            except:
                pass

        prices = sorted(list(set(prices)))

        print("=" * 40)
        print(f"DBA RAW PRICES: {prices[:50]}")
        print(f"COUNT: {len(prices)}")
        print("=" * 40)

        return prices

    except Exception as e:

        print("DBA SEARCH ERROR:", e)

        return []

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if not prices:
        return []

    if len(prices) < 3:
        return sorted(prices)

    median = statistics.median(prices)

    filtered = []

    for price in prices:

        deviation = abs(price - median) / median

        if deviation <= 0.6:

            filtered.append(price)

        else:

            print(f"OUTLIER REMOVED: {price}")

    filtered = sorted(list(set(filtered)))

    print("FILTERED:", filtered)

    return filtered

# ---------------------------------------------------
# BUILD PRICE RANGE
# ---------------------------------------------------

def build_price_range(prices):

    if not prices:
        return None

    median = statistics.median(prices)

    low = median * 0.85
    high = median * 1.15

    low = round(low / 50) * 50
    high = round(high / 50) * 50

    return f"{int(low)}-{int(high)} kr"

# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        print("=" * 40)
        print("ANALYZE START")
        print("=" * 40)

        image_bytes = await file.read()

        optimized = optimize_image(image_bytes)

        web_entities = await detect_web_entities(
            optimized
        )

        strong_design_match = extract_strong_design_match(
            web_entities
        )

        vision = await analyze_image(
            optimized,
            web_entities,
            strong_design_match
        )

        print("VISION:", vision)

        title = vision.get("title", "Ukendt")
        category = vision.get("category", "Andet")
        condition = vision.get("condition", "")

        raw_search_term = vision.get(
            "search_term",
            title
        )

        search_term = optimize_search_term(
            raw_search_term
        )

        search_term = build_smart_search_term(
            search_term
        )

        # ---------------------------------------------------
        # DIRECT DBA SCRAPE
        # ---------------------------------------------------

        prices = await dba_search(search_term)

        # fallback
        if len(prices) <= 2:

            print("=" * 40)
            print("CATEGORY FALLBACK")
            print("=" * 40)

            prices = await dba_search(
                category.lower()
            )

        print("ALL RAW:", prices)

        filtered = clean_prices(prices)

        print("FILTERED:", filtered)

        price_range = build_price_range(filtered)

        return {
            "title": title,
            "category": category,
            "condition": condition,
            "price": (
                price_range
                if price_range
                else "Ingen sikre priser fundet"
            )
        }

    except Exception as e:

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )