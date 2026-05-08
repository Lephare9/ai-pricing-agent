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

print("GEMINI:", bool(GEMINI_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))

# ---------------------------------------------------
# GEMINI
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

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

    image.thumbnail((1200, 1200))

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
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(image_bytes):

    prompt = """
Analyser objektet i centrum af billedet.

Returnér KUN valid JSON:

{
  "title": "kort dansk navn",
  "category": "kategori",
  "condition": "Brugt",
  "search_term": "meget præcis DBA søgning"
}

Regler:
- Fokusér kun på hovedobjektet
- Ignorér baggrund
- search_term skal være kort og præcis
- dansk tekst
"""

    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"
    ]

    last_error = None

    for model_name in models:

        try:

            print(f"MODEL: {model_name}")

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
            text = re.sub(r"```json|```", "", text).strip()

            print(text)

            return json.loads(text)

        except Exception as e:

            print(f"GEMINI FEJL: {e}")
            last_error = e

    raise Exception(f"ALLE MODELLER FEJLEDE: {last_error}")

# ---------------------------------------------------
# SERP SEARCH
# ---------------------------------------------------

async def serp_search(query):

    print("=" * 40)
    print(f"SEARCH: {query}")
    print("=" * 40)

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "google_domain": "google.dk",
        "num": 10
    }

    try:

        async with httpx.AsyncClient(timeout=20) as http:

            response = await http.get(
                url,
                params=params
            )

        print(f"HTTP STATUS: {response.status_code}")

        data = response.json()

        print("KEYS:", data.keys())

        if "error" in data:
            print("=" * 40)
            print("SERPAPI ERROR")
            print("=" * 40)
            print(data["error"])

        print(
            "ORGANIC COUNT:",
            len(data.get("organic_results", []))
        )

        return data

    except Exception as e:

        print("SEARCH EXCEPTION:")
        print(str(e))

        return {}

# ---------------------------------------------------
# EXTRACT PRICES
# ---------------------------------------------------

def extract_prices(data):

    text_parts = []

    for result in data.get("organic_results", []):

        text_parts.append(
            result.get("title", "")
        )

        text_parts.append(
            result.get("snippet", "")
        )

    combined = " ".join(text_parts)

    print("=" * 40)
    print("RAW SEARCH TEXT")
    print("=" * 40)
    print(combined[:3000])

    patterns = [

        r'(\d{2,5})\s?kr',

        r'(\d{2,5})\s?kroner',

        r'kr\.?\s?(\d{2,5})',

        r'(\d{2,5}),-',

        r'(\d{2,5})\s?dkk'
    ]

    prices = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            combined,
            flags=re.IGNORECASE
        )

        for m in matches:

            try:

                price = int(m)

                if 50 <= price <= 50000:
                    prices.append(price)

            except:
                pass

    prices = sorted(list(set(prices)))

    print("FOUND:", prices)

    return prices

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if not prices:
        return []

    if len(prices) < 3:
        return prices

    median = statistics.median(prices)

    filtered = [
        p for p in prices
        if median * 0.4 <= p <= median * 2.5
    ]

    print("FILTERED:", filtered)

    return filtered

# ---------------------------------------------------
# BUILD PRICE
# ---------------------------------------------------

def build_price(prices):

    if not prices:
        return "Ukendt pris"

    median = int(statistics.median(prices))

    rounded = round(median / 50) * 50

    return f"{rounded} kr"

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

        vision = await analyze_image(optimized)

        print("VISION:", vision)

        title = vision.get("title", "Ukendt objekt")
        category = vision.get("category", "")
        condition = vision.get("condition", "Brugt")

        term = vision.get("search_term", title)

        searches = [

            f"{term} DBA",

            f"{term} Facebook Marketplace",

            f"{term} GulogGratis",

            f"{term} Trendsales"
        ]

        tasks = [
            serp_search(q)
            for q in searches
        ]

        results = await asyncio.gather(*tasks)

        all_prices = []

        for r in results:

            found = extract_prices(r)

            all_prices.extend(found)

        all_prices = sorted(list(set(all_prices)))

        print("ALL:", all_prices)

        cleaned = clean_prices(all_prices)

        return {
            "title": title,
            "category": category,
            "condition": condition,
            "price": build_price(cleaned),
            "matches": len(cleaned)
        }

    except Exception as e:

        print("=" * 40)
        print("FATAL ERROR")
        print("=" * 40)

        print(str(e))

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )