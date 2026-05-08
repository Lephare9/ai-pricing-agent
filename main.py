# main.py

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

import google.generativeai as genai

import asyncio
import base64
import httpx
import json
import os
import re
import statistics


# =====================================================
# CONFIG
# =====================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not GEMINI_API_KEY:
    raise Exception("Missing GEMINI_API_KEY")

if not SERPAPI_KEY:
    raise Exception("Missing SERPAPI_KEY")

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")


# =====================================================
# FASTAPI
# =====================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# HELPERS
# =====================================================

def extract_prices(text):

    prices = []

    matches = re.findall(
        r'(\d{2,5})\s?(?:kr|,-|dkk)',
        text.lower()
    )

    for match in matches:

        try:

            price = int(match)

            if 50 <= price <= 50000:
                prices.append(price)

        except:
            pass

    return prices


def clean_prices(prices):

    if len(prices) < 3:
        return prices

    median = statistics.median(prices)

    filtered = []

    for p in prices:

        if median * 0.4 <= p <= median * 2.5:
            filtered.append(p)

    return filtered


def build_price_range(prices):

    if not prices:
        return "Ukendt pris"

    median = int(statistics.median(prices))

    low = int(round((median * 0.9) / 50) * 50)
    high = int(round((median * 1.1) / 50) * 50)

    return f"{low} - {high} kr"


# =====================================================
# GEMINI VISION
# =====================================================

async def analyze_image_with_gemini(image_bytes):

    prompt = """
    Du analyserer brugte møbler og boligobjekter i Danmark.

    Returner KUN valid JSON.

    Svarformat:

    {
      "title": "...",
      "category": "...",
      "material": "...",
      "description": "...",
      "searches": [
        "...",
        "...",
        "...",
        "...",
        "..."
      ]
    }

    Regler:
    - Alt skal være på dansk
    - Ingen engelske ord
    - Beskriv objektet præcist
    - Gæt designer/stil hvis muligt
    - Lav gode danske søgestrenge til brugtmarked
    - Fokusér på DBA/Facebook Marketplace søgninger
    - Ingen markdown
    - Ingen forklaring
    """

    image_part = {
        "mime_type": "image/jpeg",
        "data": image_bytes
    }

    response = model.generate_content(
        [
            prompt,
            image_part
        ]
    )

    text = response.text.strip()

    text = text.replace("```json", "")
    text = text.replace("```", "")

    print("GEMINI RAW:", text)

    return json.loads(text)


# =====================================================
# SERPAPI SEARCH
# =====================================================

async def search_query(client, query):

    try:

        url = "https://serpapi.com/search.json"

        params = {
            "engine": "google",
            "q": query,
            "hl": "da",
            "gl": "dk",
            "google_domain": "google.dk",
            "num": 10,
            "api_key": SERPAPI_KEY,
        }

        response = await client.get(
            url,
            params=params,
            timeout=20
        )

        data = response.json()

        prices = []

        for result in data.get("organic_results", []):

            text = (
                result.get("title", "")
                + " "
                + result.get("snippet", "")
            )

            found = extract_prices(text)

            prices.extend(found)

        print("SEARCH:", query)
        print("FOUND:", prices)

        return prices

    except Exception as e:

        print("SEARCH ERROR:", str(e))

        return []


# =====================================================
# ANALYZE
# =====================================================

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):

    try:

        image_bytes = await file.read()

        # =========================================
        # GEMINI ANALYZE
        # =========================================

        gemini_data = await analyze_image_with_gemini(
            image_bytes
        )

        print("GEMINI:", gemini_data)

        searches = gemini_data.get("searches", [])

        # =========================================
        # PARALLEL SEARCHES
        # =========================================

        async with httpx.AsyncClient() as client:

            tasks = [
                search_query(client, q)
                for q in searches[:5]
            ]

            results = await asyncio.gather(*tasks)

        # =========================================
        # COLLECT PRICES
        # =========================================

        all_prices = []

        for result in results:
            all_prices.extend(result)

        print("ALL PRICES:", all_prices)

        all_prices = clean_prices(all_prices)

        print("FILTERED:", all_prices)

        # =========================================
        # RESULT
        # =========================================

        return {
            "title": gemini_data.get("title", "Ukendt objekt"),
            "material": gemini_data.get("material", "Ukendt"),
            "condition": "Brugt med almindelige brugsspor",
            "price": build_price_range(all_prices),
            "found_prices": len(all_prices),
            "description": gemini_data.get("description", ""),
            "searches_used": searches,
        }

    except Exception as e:

        import traceback

        traceback.print_exc()

        return {
            "title": "Fejl",
            "material": "Ukendt",
            "condition": str(e),
            "price": "Ukendt pris",
            "found_prices": 0,
        }


# =====================================================
# ROOT
# =====================================================

@app.get("/")
def root():

    return {
        "status": "running"
    }