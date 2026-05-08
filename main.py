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
    return {
        "status": "ok",
        "version": "v5"
    }

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

    print(
        f"IMAGE: {len(image_bytes)} → "
        f"{len(optimized)} bytes"
    )

    return optimized

# ---------------------------------------------------
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(image_bytes):

    prompt = """
Du analyserer brugte genstande i Danmark.

Find KUN hovedobjektet i centrum.

Ignorér:
- baggrund
- dekoration
- omgivelser

Returnér KUN valid JSON:

{
  "title": "...",
  "category": "...",
  "condition": "...",
  "search_term": "..."
}

Regler:
- dansk sprog
- 2-4 ord
- konkret objekt
- samme formulering som DBA

GOD:
"zink vandkande"

DÅRLIG:
"have"
"""

    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"
    ]

    last_error = None

    for model_name in models:

        try:

            print("MODEL:", model_name)

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

            text = (
                text
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            print(text)

            return json.loads(text)

        except Exception as e:

            print(e)

            last_error = e

    raise last_error

# ---------------------------------------------------
# SEARCH
# ---------------------------------------------------

async def serp_search(query):

    print("SEARCH:", query)

    url = "https://serpapi.com/search.json"

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "google_domain": "google.dk",
        "gl": "dk",
        "hl": "da",
        "num": 10
    }

    async with httpx.AsyncClient(timeout=15) as http:

        response = await http.get(
            url,
            params=params
        )

    return response.json()

# ---------------------------------------------------
# PRICE EXTRACTION
# ---------------------------------------------------

def extract_prices(data):

    prices = []

    sources = []

    for r in data.get("organic_results", []):

        sources.append(r.get("title", ""))
        sources.append(r.get("snippet", ""))

        try:

            rich = r.get("rich_snippet", {})

            top = rich.get("top", {})

            detected = top.get(
                "detected_extensions",
                {}
            )

            raw_price = detected.get("price")

            if raw_price:

                number = re.sub(
                    r"[^\d]",
                    "",
                    raw_price
                )

                if number:

                    price = int(number)

                    if 50 <= price <= 50000:

                        prices.append(price)

        except:
            pass

    combined = " ".join(sources).lower()

    patterns = [
        r"(\d{1,3}(?:\.\d{3})+)\s*(?:kr|dkk|,-)",
        r"(\d{3,6})\s*(?:kr|dkk|,-)",
        r"(?:kr|dkk)\s*(\d{1,3}(?:\.\d{3})+)",
        r"(?:kr|dkk)\s*(\d{3,6})",
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

    return prices

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if len(prices) < 2:
        return prices

    median = statistics.median(prices)

    filtered = [
        p for p in prices
        if median * 0.4 <= p <= median * 2.2
    ]

    return filtered

# ---------------------------------------------------
# BUILD PRICE
# ---------------------------------------------------

def build_price(prices):

    if not prices:
        return "Ukendt pris"

    median = int(statistics.median(prices))

    low = int(round((median * 0.9) / 50) * 50)

    high = int(round((median * 1.1) / 50) * 50)

    if low == high:
        return f"{low} kr"

    return f"{low} – {high} kr"

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

        title = vision.get(
            "title",
            "Ukendt objekt"
        )

        category = vision.get(
            "category",
            ""
        )

        condition = vision.get(
            "condition",
            "Brugt stand"
        )

        search_term = vision.get(
            "search_term",
            title
        )

        # -------------------------------------
        # ONLY MARKETPLACE SEARCHES
        # -------------------------------------

        queries = [
            f"site:dba.dk {search_term}",
            f"site:facebook.com/marketplace {search_term}",
            f"site:guloggratis.dk {search_term}",
            f"site:trendsales.dk {search_term}"
        ]

        tasks = [
            serp_search(q)
            for q in queries
        ]

        results = await asyncio.gather(*tasks)

        # -------------------------------------
        # EXTRACT PRICES
        # -------------------------------------

        all_prices = []

        for r in results:

            found = extract_prices(r)

            print("FOUND:", found)

            all_prices.extend(found)

        all_prices = list(set(all_prices))

        print("ALL:", sorted(all_prices))

        all_prices = clean_prices(all_prices)

        print("FILTERED:", sorted(all_prices))

        return {
            "title": title,
            "category": category,
            "condition": condition,
            "price": build_price(all_prices),
            "matches": len(all_prices)
        }

    except Exception as e:

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )