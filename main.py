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
SERPAPI_KEY    = os.getenv("SERPAPI_KEY")

print("GEMINI:", bool(GEMINI_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))

# ---------------------------------------------------
# GEMINI CLIENT
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():
    return {
        "status": "ok",
        "version": "v6"
    }

# ---------------------------------------------------
# IMAGE OPTIMIZATION
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

    return optimized

# ---------------------------------------------------
# GEMINI ANALYZE
# ---------------------------------------------------

async def analyze_image(image_bytes):

    prompt = """
Du analyserer brugte genstande i Danmark.

Fokusér KUN på hovedobjektet i midten af billedet.

Returnér KUN valid JSON.

Format:

{
  "title": "kort navn",
  "category": "kategori",
  "condition": "Brugt",
  "search_term": "mest præcise DBA søgning"
}

Regler:
- KUN ét objekt
- Korte danske navne
- search_term skal ligne noget folk søger på DBA

Eksempel:

{
  "title": "Rattan lænestol",
  "category": "Lænestole",
  "condition": "Brugt",
  "search_term": "Rattan lænestol"
}
"""

    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"
    ]

    last_error = None

    for model_name in models:

        try:

            print("=" * 40)
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

            text = re.sub(
                r"```json|```",
                "",
                text
            ).strip()

            print(text)

            return json.loads(text)

        except Exception as e:

            print(f"MODEL ERROR: {e}")

            last_error = e

    raise Exception(last_error)

# ---------------------------------------------------
# SERPAPI SEARCH
# ---------------------------------------------------

async def serp_search(query):

    searches = [

        f"{query} DBA",

        f"{query} Facebook Marketplace",

        f"{query} GulogGratis",

        f"{query} Trendsales"

    ]

    results = []

    async with httpx.AsyncClient(timeout=20) as http:

        for q in searches:

            print("=" * 40)
            print(f"SEARCH: {q}")

            params = {
                "engine": "google",
                "q": q,
                "api_key": SERPAPI_KEY,
                "google_domain": "google.dk",
                "gl": "dk",
                "hl": "da",
                "num": 10
            }

            try:

                response = await http.get(
                    "https://serpapi.com/search.json",
                    params=params
                )

                data = response.json()

                print("KEYS:", data.keys())

                organic = data.get(
                    "organic_results",
                    []
                )

                print(
                    "ORGANIC COUNT:",
                    len(organic)
                )

                for r in organic[:3]:

                    print("--- RESULT ---")

                    print(
                        "TITLE:",
                        r.get("title")
                    )

                    print(
                        "SNIPPET:",
                        r.get("snippet")
                    )

                results.append(data)

            except Exception as e:

                print(f"SEARCH ERROR: {e}")

    return results

# ---------------------------------------------------
# EXTRACT PRICES
# ---------------------------------------------------

def extract_prices_from_results(data):

    prices = []

    texts = []

    # ORGANIC RESULTS
    for r in data.get("organic_results", []):

        texts.append(
            str(r.get("title", ""))
        )

        texts.append(
            str(r.get("snippet", ""))
        )

        if "rich_snippet" in r:

            texts.append(
                json.dumps(r["rich_snippet"])
            )

    # SHOPPING RESULTS
    for r in data.get("shopping_results", []):

        texts.append(
            str(r.get("title", ""))
        )

        texts.append(
            str(r.get("price", ""))
        )

    combined = "\n".join(texts)

    print("=" * 40)
    print("RAW SEARCH TEXT")
    print("=" * 40)

    print(combined[:4000])

    patterns = [

        # 2.500 kr
        r'(\d{1,3}(?:[., ]\d{3})+)\s*(?:kr|KR|Kr|dkk|DKK)',

        # kr 2.500
        r'(?:kr|KR|Kr|dkk|DKK)\s*(\d{1,3}(?:[., ]\d{3})+)',

        # 2500 kr
        r'(\d{3,6})\s*(?:kr|KR|Kr|dkk|DKK)',

        # kr 2500
        r'(?:kr|KR|Kr|dkk|DKK)\s*(\d{3,6})',

        # 2 500
        r'(\d{1,3}(?: \d{3})+)',

    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            combined
        )

        for raw in matches:

            try:

                cleaned = (
                    raw.replace(".", "")
                       .replace(",", "")
                       .replace(" ", "")
                )

                price = int(cleaned)

                if 50 <= price <= 50000:
                    prices.append(price)

            except:
                pass

    prices = sorted(
        list(set(prices))
    )

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

    median = int(
        statistics.median(prices)
    )

    low = int(
        round((median * 0.85) / 50) * 50
    )

    high = int(
        round((median * 1.15) / 50) * 50
    )

    if low == high:
        return f"{low} kr"

    return f"{low} - {high} kr"

# ---------------------------------------------------
# MAIN ANALYZE ENDPOINT
# ---------------------------------------------------

@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...)
):

    try:

        print("=" * 40)
        print("ANALYZE START")
        print("=" * 40)

        image_bytes = await file.read()

        optimized = optimize_image(
            image_bytes
        )

        # GEMINI
        vision = await analyze_image(
            optimized
        )

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
            "Brugt"
        )

        search_term = vision.get(
            "search_term",
            title
        )

        # SEARCH
        results = await serp_search(
            search_term
        )

        all_prices = []

        for result in results:

            found = extract_prices_from_results(
                result
            )

            all_prices.extend(found)

        all_prices = sorted(
            list(set(all_prices))
        )

        print("ALL:", all_prices)

        all_prices = clean_prices(
            all_prices
        )

        return {

            "title": title,

            "category": category,

            "condition": condition,

            "price": build_price(
                all_prices
            ),

            "matches": len(all_prices)

        }

    except Exception as e:

        print("=" * 40)
        print("FULL ERROR")
        print("=" * 40)

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )