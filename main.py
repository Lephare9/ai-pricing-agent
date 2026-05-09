from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from google import genai
from google.genai import types

from PIL import Image

import asyncio
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
# GEMINI CLIENT
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# DESIGNER BRANDS
# ---------------------------------------------------

HIGH_VALUE_DESIGN = [
    "hay",
    "mater",
    "wegner",
    "fritz hansen",
    "carl hansen",
    "pp møbler",
    "boconcept",
    "montana",
    "gubi",
    "eames",
    "kartell"
]

HIGH_VALUE_FURNITURE = [
    "stol",
    "lænestol",
    "barstol",
    "sofa",
    "bord",
    "spisebord",
    "designerstol"
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
# GOOGLE VISION WEB DETECTION
# ---------------------------------------------------

async def detect_web_entities(image_bytes):

    try:

        print("=" * 40)
        print("VISION WEB DETECTION")
        print("=" * 40)

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

                # kun relativt sikre entities
                if score >= 0.70 and len(desc) > 2:

                    entities.append({
                        "name": desc,
                        "score": score
                    })

        except:
            pass

        print("WEB ENTITIES:")
        print(entities)

        return entities

    except Exception as e:

        print("VISION ERROR:")
        print(e)

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

- Ignorér objekter i baggrunden
- Fokusér KUN på hovedobjektet i centrum
- Gæt ALDRIG designer eller brand hvis du er usikker
- Brug kun designer/brand hvis sandsynligheden er høj
- Hvis du er usikker:
  brug generisk titel i stedet

Returnér KUN valid JSON:

{{
  "title": "Kort præcist navn",
  "category": "Kategori",
  "condition": "Kort vurdering af stand og evt fejl",
  "search_term": "Meget præcis DBA søgning"
}}

Regler:
- Dansk
- Kort title
- search_term skal være realistisk
- Ingen overdreven designer-gætning
"""

    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash"
    ]

    for model_name in models:

        try:

            print("=" * 40)
            print(f"MODEL: {model_name}")
            print("=" * 40)

            response = client.models.generate_content(
                model=model_name,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg"
                    )
                ]
            )

            text = response.text.strip()

            text = re.sub(
                r"```json|```",
                "",
                text
            ).strip()

            print(text)

            return json.loads(text)

        except Exception as e:

            print(f"MODEL ERROR: {e}")

    raise Exception("Gemini failed")

# ---------------------------------------------------
# SEARCH
# ---------------------------------------------------

async def serp_search(query, source):

    try:

        print("=" * 40)
        print(f"SEARCH: {query} {source}")
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

        url = "https://serpapi.com/search.json"

        params = {
            "engine": "google",
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

        print("SEARCH ERROR:")
        print(e)

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
    print(combined[:6000])

    combined = combined.lower()

    patterns = [

        r"(\d{1,3}(?:[.,]\d{3})*)\s?kr",

        r"dkk\s?(\d{1,3}(?:[.,]\d{3})*)",

        r"(\d{1,3}(?:[.,]\d{3})*)\s?dkk"
    ]

    blocked_before = [
        "str",
        "størrelse",
        "size",
        "nr",
        "model"
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

    if len(prices) < 4:
        return sorted(prices)

    med = statistics.median(prices)

    if med <= 0:
        return sorted(prices)

    filtered = []

    for price in prices:

        deviation = abs(price - med) / med

        # max 100% fra median
        if deviation <= 1.0:

            filtered.append(price)

        else:

            print(
                f"OUTLIER REMOVED: "
                f"{price} "
                f"(median: {round(med)})"
            )

    if len(filtered) < 2:

        print("FILTER TOO AGGRESSIVE → USING ORIGINAL")

        return sorted(prices)

    filtered = sorted(list(set(filtered)))

    print("FILTERED:", filtered)

    return filtered

# ---------------------------------------------------
# BUILD PRICE
# ---------------------------------------------------

def build_price(prices):

    if not prices:
        return None

    median = statistics.median(prices)

    if median < 200:
        rounded = round(median / 10) * 10
    else:
        rounded = round(median / 50) * 50

    return int(rounded)

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

    # for billigt til premium design
    if median_price < 1200:

        print("=" * 40)
        print("DESIGN REJECTED")
        print(
            f"{detected_brand} rejected "
            f"(median {median_price})"
        )
        print("=" * 40)

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

        return cleaned

    return title

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

        # vision web detection
        web_entities = await detect_web_entities(
            optimized
        )

        # gemini
        vision = await analyze_image(
            optimized,
            web_entities
        )

        print("VISION:", vision)

        title = vision.get("title", "Ukendt")
        category = vision.get("category", "Andet")
        condition = vision.get("condition", "")
        search_term = vision.get("search_term", title)

        tasks = [

            serp_search(search_term, "DBA"),
            serp_search(search_term, "Marketplace"),
            serp_search(search_term, "Lauritz"),
            serp_search(search_term, "GulogGratis")
        ]

        results = await asyncio.gather(*tasks)

        all_prices = []

        for result in results:

            prices = extract_prices(result)

            all_prices.extend(prices)

        all_prices = sorted(list(set(all_prices)))

        print("ALL:", all_prices)

        filtered = clean_prices(all_prices)

        median_price = build_price(filtered)

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
                f"{median_price} kr"
                if median_price
                else None
            )
        }

    except Exception as e:

        print("=" * 40)
        print("FATAL ERROR")
        print("=" * 40)

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )