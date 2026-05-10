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
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY")

print("GEMINI:", bool(GEMINI_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))
print("VISION:", bool(GOOGLE_VISION_API_KEY))

# ---------------------------------------------------
# GEMINI
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# DESIGN BRANDS
# ---------------------------------------------------

HIGH_VALUE_DESIGN = [
    "hay",
    "mater",
    "wegner",
    "fritz hansen",
    "carl hansen",
    "pp møbler",
    "montana",
    "gubi",
    "eames",
    "kartell",
    "louis poulsen",
]

HIGH_VALUE_FURNITURE = [
    "stol",
    "barstol",
    "lænestol",
    "sofa",
    "bord",
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
# GOOGLE VISION WEB DETECTION
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
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(image_bytes, web_entities):

    prompt = f"""
Du analyserer brugte genstande i Danmark.

Google Vision entities:
{web_entities}

VIGTIGT:

- Fokusér kun på hovedobjektet
- Ignorér baggrund
- Gæt ikke designer hvis usikker

MEGET VIGTIGT:

search_term skal ligne almindelige ord
fra DBA annoncer.

Brug IKKE:
- fagtermer
- designtermer
- arkitektord
- tekniske beskrivelser

Brug simple folkelige ord.

Eksempel:
- "formspændt stol" → "spisebordsstol"
- "modulsofa" → "sofa"
- "skulpturel lampe" → "bordlampe"

Search_term må IKKE indeholde:
- farver
- stand
- størrelser
- pyntetekst

Returnér KUN valid JSON:

{{
  "title": "Kort titel",
  "category": "Kategori",
  "condition": "Kort vurdering",
  "search_term": "Folkelig DBA søgning"
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
# SOURCE ROUTING
# ---------------------------------------------------

def get_sources(category):

    category = category.lower()

    # TØJ
    if any(word in category for word in [
        "jakke",
        "tøj",
        "blazer",
        "sko",
        "mode",
        "kjole",
        "shirt",
        "bukser"
    ]):

        return [
            "Trendsales",
            "DBA"
        ]

    # MØBLER
    if any(word in category for word in [
        "sofa",
        "stol",
        "bord",
        "lænestol",
        "barstol",
        "puf",
        "skammel",
        "fodskammel"
    ]):

        return [
            "DBA",
            "Marketplace",
            "Lauritz"
        ]

    # DESIGN / KUNST
    if any(word in category for word in [
        "kunst",
        "litografi",
        "plakat",
        "maleri",
        "lampe",
        "vase"
    ]):

        return [
            "Lauritz",
            "DBA"
        ]

    # DEFAULT
    return [
        "DBA",
        "Marketplace",
        "GulogGratis"
    ]

# ---------------------------------------------------
# SEARCH
# ---------------------------------------------------

async def serp_search(query, source, engine="google_light"):

    try:

        print("=" * 40)
        print(f"SEARCH: {query} {source}")
        print(f"ENGINE: {engine}")
        print("=" * 40)

        q = query

        if source == "DBA":
            q += " site:dba.dk"

        elif source == "Marketplace":
            q += " site:facebook.com/marketplace Danmark"

        elif source == "Lauritz":
            q += " site:lauritz.com hammer"

        elif source == "GulogGratis":
            q += " site:guloggratis.dk"

        elif source == "Trendsales":
            q += " site:vinted.dk"

        url = "https://serpapi.com/search.json"

        params = {
            "engine": engine,
            "q": q,
            "api_key": SERPAPI_KEY,
            "google_domain": "google.dk",
            "gl": "dk",
            "hl": "da",
            "num": 10
        }

        async with httpx.AsyncClient(timeout=20) as http:

            response = await http.get(
                url,
                params=params
            )

        data = response.json()

        organic = data.get("organic_results", [])

        print(f"ORGANIC COUNT: {len(organic)}")

        return {
            "source": source,
            "data": data
        }

    except Exception as e:

        print("SEARCH ERROR:", e)

        return {
            "source": source,
            "data": {}
        }

# ---------------------------------------------------
# EXTRACT PRICES
# ---------------------------------------------------

def extract_prices(result):

    source = result["source"]
    data = result["data"]

    prices = []

    organic = data.get("organic_results", [])

    text_parts = []

    for item in organic:

        text_parts.append(item.get("title", ""))
        text_parts.append(item.get("snippet", ""))

    combined = " ".join(text_parts)

    print("=" * 40)
    print(f"RAW SEARCH TEXT [{source}]")
    print("=" * 40)
    print(combined[:5000])

    combined = combined.lower()

    patterns = [
        r"(\d{1,3}(?:[.,]\d{3})*)\s?kr",
        r"dkk\s?(\d{1,3}(?:[.,]\d{3})*)",
    ]

    blocked_before = [
        "str",
        "størrelse",
        "size",
        "model",
    ]

    for pattern in patterns:

        matches = re.finditer(pattern, combined)

        for match in matches:

            try:

                start = max(0, match.start() - 15)

                context = combined[start:match.start()]

                if any(word in context for word in blocked_before):
                    continue

                raw = match.group(1)

                raw = raw.replace(".", "")
                raw = raw.replace(",", "")

                price = int(raw)

                if 50 <= price <= 250000:
                    prices.append(price)

            except:
                pass

    prices = sorted(list(set(prices)))

    print(f"FOUND [{source}]: {prices}")

    return prices

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

    if len(filtered) < 2:

        print("=" * 40)
        print("FILTER TOO AGGRESSIVE")
        print("USING ORIGINAL PRICES")
        print("=" * 40)

        return sorted(prices)

    filtered = sorted(list(set(filtered)))

    print("=" * 40)
    print("FILTERED:", filtered)
    print("=" * 40)

    return filtered

# ---------------------------------------------------
# BUILD PRICE RANGE
# ---------------------------------------------------

def build_price_range(prices):

    if not prices:
        return None

    median = statistics.median(prices)

    if median < 500:

        low = median - 100
        high = median + 100

    elif median < 2000:

        low = median * 0.8
        high = median * 1.2

    else:

        low = median * 0.85
        high = median * 1.15

    # bredere interval ved få priser
    if len(prices) <= 3:

        low *= 0.9
        high *= 1.1

    # rounding
    if median < 200:

        low = round(low / 10) * 10
        high = round(high / 10) * 10

    else:

        low = round(low / 50) * 50
        high = round(high / 50) * 50

    low = max(0, int(low))
    high = int(high)

    return f"{low}-{high} kr"

# ---------------------------------------------------
# DESIGN VALIDATION
# ---------------------------------------------------

def validate_design_prediction(
    title,
    category,
    median_price
):

    if not median_price:
        return title

    title_lower = title.lower()
    category_lower = category.lower()

    detected_brand = None

    for brand in HIGH_VALUE_DESIGN:

        if brand in title_lower:
            detected_brand = brand
            break

    if not detected_brand:
        return title

    is_furniture = any(
        word in category_lower
        for word in HIGH_VALUE_FURNITURE
    )

    if not is_furniture:
        return title

    if median_price >= 1800:
        return title

    if 1000 <= median_price < 1800:

        if not title.lower().startswith("muligvis"):
            return f"Muligvis {title}"

        return title

    cleaned = title

    for brand in HIGH_VALUE_DESIGN:

        cleaned = re.sub(
            brand,
            "",
            cleaned,
            flags=re.IGNORECASE
        )

    cleaned = re.sub(
        r"\s+",
        " ",
        cleaned
    ).strip()

    return f"{cleaned} (muligt design)"

# ---------------------------------------------------
# EARLY STOP
# ---------------------------------------------------

def enough_prices(prices):

    if len(prices) < 6:
        return False

    median = statistics.median(prices)

    deviations = []

    for price in prices:

        deviation = abs(price - median) / median

        deviations.append(deviation)

    avg_dev = statistics.mean(deviations)

    print("=" * 40)
    print("EARLY STOP CHECK")
    print(f"COUNT: {len(prices)}")
    print(f"AVG DEV: {round(avg_dev, 2)}")
    print("=" * 40)

    return avg_dev < 0.35

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

        vision = await analyze_image(
            optimized,
            web_entities
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

        category_search = category.lower()

        sources = get_sources(category)

        print("SOURCES:", sources)

        all_prices = []

        for source in sources:

            # FIRST TRY → GOOGLE LIGHT
            result = await serp_search(
                search_term,
                source,
                engine="google_light"
            )

            prices = extract_prices(result)

            # FALLBACK → NORMAL GOOGLE
            if len(prices) <= 1:

                print("=" * 40)
                print("FALLBACK TO GOOGLE")
                print("=" * 40)

                result = await serp_search(
                    search_term,
                    source,
                    engine="google"
                )

                prices = extract_prices(result)

            # FALLBACK → CATEGORY SEARCH
            if (
                len(prices) <= 1
                and search_term != category_search
            ):

                print("=" * 40)
                print("FALLBACK TO CATEGORY SEARCH")
                print(f"{search_term} → {category_search}")
                print("=" * 40)

                result = await serp_search(
                    category_search,
                    source,
                    engine="google"
                )

                prices = extract_prices(result)

            all_prices.extend(prices)

            all_prices = sorted(
                list(set(all_prices))
            )

            print("CURRENT PRICES:", all_prices)

            # EARLY STOP
            if enough_prices(all_prices):

                print("=" * 40)
                print("EARLY STOP ACTIVATED")
                print("=" * 40)

                break

        print("ALL:", all_prices)

        filtered = clean_prices(all_prices)

        price_range = build_price_range(filtered)

        median_price = (
            statistics.median(filtered)
            if filtered
            else None
        )

        title = validate_design_prediction(
            title,
            category,
            median_price
        )

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