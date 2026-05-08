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

print("GEMINI:", bool(GEMINI_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))

# ---------------------------------------------------
# GEMINI CLIENT
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# REGEX
# ---------------------------------------------------

PRICE_REGEX = r"(\d{2,6})\s?(kr|dkk|,-)?"

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok"}

# ---------------------------------------------------
# IMAGE OPTIMIZATION
# ---------------------------------------------------

def optimize_image(image_bytes):

    image = Image.open(io.BytesIO(image_bytes))

    image = image.convert("RGB")

    max_size = 1400

    image.thumbnail((max_size, max_size))

    output = io.BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=72,
        optimize=True
    )

    optimized = output.getvalue()

    print("ORIGINAL SIZE:", len(image_bytes))
    print("OPTIMIZED SIZE:", len(optimized))

    return optimized

# ---------------------------------------------------
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(image_bytes):

    print("=" * 50)
    print("START GEMINI ANALYZE")
    print("=" * 50)

    print("FINAL SIZE SENT TO GEMINI:", len(image_bytes))

    prompt = """
Du analyserer brugte møbler i Danmark.

Returnér KUN valid JSON.

Format:

{
  "title": "...",
  "category": "...",
  "condition": "...",
  "search_terms": [
    "...",
    "...",
    "..."
  ]
}

Regler:
- Alt skal være dansk
- Ingen engelske ord
- Fokus på DBA/Facebook Marketplace
- Korte præcise søgninger
"""

    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"
    ]

    last_error = None

    for model_name in models:

        try:

            print(f"TRYING MODEL: {model_name}")

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

            print(f"SUCCESS WITH: {model_name}")

            text = response.text.strip()

            text = text.replace("```json", "")
            text = text.replace("```", "")

            print("RAW GEMINI:")
            print(text)

            return json.loads(text)

        except Exception as e:

            print("=" * 50)
            print(f"MODEL FAILED: {model_name}")
            print(str(e))
            print("=" * 50)

            last_error = e

            continue

    raise Exception(f"ALL GEMINI MODELS FAILED: {last_error}")

# ---------------------------------------------------
# SERPAPI SEARCH
# ---------------------------------------------------

async def serp_search(query):

    print("SEARCH:", query)

    url = "https://serpapi.com/search.json"

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": "da",
        "gl": "dk",
        "google_domain": "google.dk"
    }

    async with httpx.AsyncClient(timeout=20) as client_http:

        response = await client_http.get(
            url,
            params=params
        )

    data = response.json()

    return data

# ---------------------------------------------------
# EXTRACT PRICES
# ---------------------------------------------------

def extract_prices(data):

    text = str(data).lower()

    matches = re.findall(PRICE_REGEX, text)

    prices = []

    for match in matches:

        try:

            price = int(match[0])

            if 50 <= price <= 100000:
                prices.append(price)

        except:
            pass

    return prices

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if len(prices) < 3:
        return prices

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        if median * 0.4 <= p <= median * 2.5:
            filtered.append(p)

    return filtered

# ---------------------------------------------------
# BUILD RANGE
# ---------------------------------------------------

def build_price(prices):

    if not prices:
        return "Ukendt pris"

    median = int(statistics.median(prices))

    low = int(round((median * 0.9) / 50) * 50)
    high = int(round((median * 1.1) / 50) * 50)

    return f"{low} - {high} kr"

# ---------------------------------------------------
# ANALYZE
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        print("=" * 50)
        print("START ANALYZE")
        print("=" * 50)

        image_bytes = await file.read()

        # ----------------------------------------
        # OPTIMIZE IMAGE
        # ----------------------------------------

        optimized = optimize_image(image_bytes)

        # ----------------------------------------
        # GEMINI ANALYSIS
        # ----------------------------------------

        vision = await analyze_image(optimized)

        print("VISION RESULT:")
        print(vision)

        title = vision.get("title", "Ukendt objekt")
        category = vision.get("category", "")
        condition = vision.get(
            "condition",
            "Brugt stand"
        )

        search_terms = vision.get(
            "search_terms",
            []
        )

        print("SEARCH TERMS:")
        print(search_terms)

        # ----------------------------------------
        # PARALLEL SEARCHES
        # ----------------------------------------

        tasks = []

        for q in search_terms:

            query = f"{q} brugt dba facebook marketplace"

            tasks.append(
                serp_search(query)
            )

        results = await asyncio.gather(*tasks)

        print("SEARCH RESULTS:", len(results))

        # ----------------------------------------
        # PRICE EXTRACTION
        # ----------------------------------------

        prices = []

        for result in results:

            found = extract_prices(result)

            print("FOUND:", found[:20])

            prices.extend(found)

        prices = list(set(prices))

        print("ALL PRICES:", prices)

        # ----------------------------------------
        # FILTER
        # ----------------------------------------

        prices = clean_prices(prices)

        print("FILTERED:", prices)

        # ----------------------------------------
        # RESPONSE
        # ----------------------------------------

        return {
            "title": title,
            "category": category,
            "condition": condition,
            "price": build_price(prices),
            "matches": len(prices)
        }

    except Exception as e:

        print("=" * 50)
        print("FULL ERROR")
        print("=" * 50)

        print(str(e))

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )