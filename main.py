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
SERPAPI_KEY    = os.getenv("SERPAPI_KEY")

print("GEMINI KEY:", bool(GEMINI_API_KEY))
print("SERPAPI KEY:", bool(SERPAPI_KEY))

# ---------------------------------------------------
# GEMINI CLIENT
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok", "version": "v4"}

# ---------------------------------------------------
# IMAGE OPTIMIZATION
# ---------------------------------------------------

def optimize_image(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    image = image.convert("RGB")
    image.thumbnail((1200, 1200))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=72, optimize=True)
    optimized = output.getvalue()
    print(f"BILLEDE: {len(image_bytes)} → {len(optimized)} bytes")
    return optimized

# ---------------------------------------------------
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(image_bytes):

    print("=" * 40)
    print("GEMINI START")
    print("=" * 40)

    prompt = """
Du analyserer brugte genstande til salg i en genbrugsbutik i Danmark.

Returnér KUN valid JSON i dette format:

{
  "title": "Kort dansk navn på genstanden (2-4 ord)",
  "category": "møbel / tøj / elektronik / køkken / kunst / legetøj / accessories / andet",
  "condition": "God stand / Brugt stand / Slidt stand",
  "search_terms": [
    "præcist søgeord 1",
    "præcist søgeord 2",
    "præcist søgeord 3"
  ]
}

Regler:
- Alt på dansk
- search_terms: korte, præcise søgeord som en dansker ville søge på DBA.dk
- Ingen engelske ord i search_terms
- Eksempel: ["rattan lænestol", "flettestol", "kurvestol"]
"""

    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ]

    last_error = None

    for model_name in models:
        try:
            print(f"PRØVER MODEL: {model_name}")

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

            print("GEMINI RAW:")
            print(text)

            return json.loads(text)

        except Exception as e:
            print(f"MODEL FEJL ({model_name}): {e}")
            last_error = e
            continue

    raise Exception(f"ALLE GEMINI MODELLER FEJLEDE: {last_error}")

# ---------------------------------------------------
# SERPAPI SEARCH — SPECIFIK
# ---------------------------------------------------

async def serp_search(query, search_type="dba"):

    print(f"SØGER [{search_type}]: {query}")

    url = "[serpapi.com](https://serpapi.com/search.json)"

    if search_type == "dba":
        # Søg direkte på DBA for præcise priser
        q = f"site:dba.dk {query}"
    elif search_type == "trendsales":
        q = f"site:trendsales.dk {query}"
    else:
        q = f"{query} pris til salg"

    params = {
        "q":             q,
        "api_key":       SERPAPI_KEY,
        "hl":            "da",
        "gl":            "dk",
        "google_domain": "google.dk",
        "num":           10
    }

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get(url, params=params)

        data = response.json()
        return data

    except Exception as e:
        print(f"SØGNING FEJL: {e}")
        return {}

# ---------------------------------------------------
# EXTRACT PRICES — FORBEDRET
# ---------------------------------------------------

def extract_prices_from_results(data):
    """
    Parser kun organic_results og shopping_results
    for at undgå støj fra resten af JSON.
    Håndterer format: 1.500 kr / 1500 kr / 1500,- / kr 1500
    """

    prices = []

    # Kombiner titler og snippets fra organiske resultater
    sources = []

    for r in data.get("organic_results", []):
        sources.append(r.get("title", ""))
        sources.append(r.get("snippet", ""))
        sources.append(r.get("price", ""))

    for r in data.get("shopping_results", []):
        sources.append(r.get("title", ""))
        sources.append(r.get("price", ""))

    combined = " ".join(sources).lower()

    # Match: 1.500 kr / 1500 kr / 1500,- / kr 1.500
    # Fjerner punktum som tusindtalsseparator
    patterns = [
        r"(\d{1,3}(?:\.\d{3})+)\s*(?:kr|dkk|,-)",   # 1.500 kr
        r"(\d{3,6})\s*(?:kr|dkk|,-)",                  # 1500 kr
        r"(?:kr|dkk)\s*(\d{1,3}(?:\.\d{3})+)",         # kr 1.500
        r"(?:kr|dkk)\s*(\d{3,6})",                      # kr 1500
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, combined):
            raw = match.group(1).replace(".", "")
            try:
                price = int(raw)
                if 50 <= price <= 50000:
                    prices.append(price)
            except:
                pass

    print(f"  → FANDT {len(prices)} priser: {sorted(set(prices))[:15]}")
    return prices

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):
    if len(prices) < 2:
        return prices

    med = statistics.median(prices)

    filtered = [
        p for p in prices
        if med * 0.35 <= p <= med * 3.0
    ]

    return filtered

# ---------------------------------------------------
# BUILD PRICE RANGE
# ---------------------------------------------------

def build_price(prices):
    if not prices:
        return "Ukendt pris"

    med   = int(statistics.median(prices))
    low   = int(round((med * 0.85) / 50) * 50)
    high  = int(round((med * 1.15) / 50) * 50)

    if low == high:
        return f"{low} kr"

    return f"{low} – {high} kr"

# ---------------------------------------------------
# MAIN ENDPOINT
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        print("=" * 40)
        print("ANALYZE START")
        print("=" * 40)

        image_bytes = await file.read()
        optimized   = optimize_image(image_bytes)

        # Gemini vision
        vision = await analyze_image(optimized)

        print("VISION:")
        print(vision)

        title       = vision.get("title",       "Ukendt objekt")
        category    = vision.get("category",    "")
        condition   = vision.get("condition",   "Brugt stand")
        search_terms = vision.get("search_terms", [title])

        print("SØGEORD:", search_terms)

        # Parallelle søgninger
        tasks = []

        for term in search_terms[:3]:
            tasks.append(serp_search(term, "dba"))

        # Tilføj generel søgning på første term
        tasks.append(serp_search(search_terms[0], "general"))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Udtræk priser
        all_prices = []

        for r in results:
            if isinstance(r, Exception):
                print("SØGNING FEJL:", r)
                continue
            found = extract_prices_from_results(r)
            all_prices.extend(found)

        all_prices = list(set(all_prices))
        print("ALLE PRISER:", sorted(all_prices))

        all_prices = clean_prices(all_prices)
        print("RENSEDE PRISER:", sorted(all_prices))

        return {
            "title":     title,
            "category":  category,
            "condition": condition,
            "price":     build_price(all_prices),
            "matches":   len(all_prices)
        }

    except Exception as e:

        print("FEJL:")
        print(str(e))
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error":   str(e)
            }
        )
