from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from google import genai
from google.genai import types

from PIL import Image

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

client = genai.Client(
    api_key=GEMINI_API_KEY
)

# ---------------------------------------------------
# ROOT
# ---------------------------------------------------

@app.get("/")
async def root():

    return {
        "status": "ok"
    }

# ---------------------------------------------------
# IMAGE OPTIMIZATION
# ---------------------------------------------------

def optimize_image(image_bytes):

    image = Image.open(
        io.BytesIO(image_bytes)
    )

    image = image.convert("RGB")

    image.thumbnail((1200,1200))

    output = io.BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=72,
        optimize=True
    )

    optimized = output.getvalue()

    print("=" * 40)
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
Analyser hovedobjektet
i centrum af billedet.

Returnér KUN valid JSON:

{
  "title": "...",
  "category": "...",
  "condition": "...",
  "search_term": "..."
}

Regler:
- dansk sprog
- kort titel
- præcis DBA-lignende søgning
- ignorér baggrund
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

            print(e)

            last_error = e

    raise Exception(last_error)

# ---------------------------------------------------
# SEARCH
# ---------------------------------------------------

async def serp_search(query):

    searches = [

        {
            "source": "DBA",
            "query": f"{query} DBA"
        },

        {
            "source": "Marketplace",
            "query": f"{query} Facebook Marketplace"
        },

        {
            "source": "GulogGratis",
            "query": f"{query} GulogGratis"
        },

        {
            "source": "Lauritz",
            "query": f"{query} Lauritz solgt"
        }

    ]

    results = []

    async with httpx.AsyncClient(
        timeout=20
    ) as http:

        for item in searches:

            print("=" * 40)
            print(
                f"SEARCH: {item['query']}"
            )

            params = {
                "engine": "google",
                "q": item["query"],
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

                organic = data.get(
                    "organic_results",
                    []
                )

                print(
                    "ORGANIC COUNT:",
                    len(organic)
                )

                results.append({

                    "source": item["source"],

                    "data": data

                })

            except Exception as e:

                print(
                    f"SEARCH ERROR: {e}"
                )

    return results

# ---------------------------------------------------
# EXTRACT PRICES
# ---------------------------------------------------

def extract_prices(source, data):

    prices = []

    texts = []

    bad_words = [

        "current bid",

        "next bid",

        "estimate",

        "vurdering",

        "starting bid",

        "minimum bid"

    ]

    lauritz_good_words = [

        "solgt for",

        "hammer price",

        "hammerslag",

        "final price"

    ]

    for result in data.get(
        "organic_results",
        []
    ):

        title = result.get(
            "title",
            ""
        )

        snippet = result.get(
            "snippet",
            ""
        )

        lower = (
            title + " " + snippet
        ).lower()

        # -----------------------------------
        # SKIP DBA CATEGORY PAGES
        # -----------------------------------

        if "På DBA finder du" in snippet:
            continue

        # -----------------------------------
        # SKIP BAD AUCTION WORDS
        # -----------------------------------

        if any(
            word in lower
            for word in bad_words
        ):
            continue

        # -----------------------------------
        # LAURITZ RULES
        # -----------------------------------

        if source == "Lauritz":

            if not any(
                word in lower
                for word in lauritz_good_words
            ):
                continue

        texts.append(title)

        texts.append(snippet)

    combined = " ".join(texts)

    print("=" * 40)
    print(f"RAW SEARCH TEXT [{source}]")
    print("=" * 40)

    print(combined[:4000])

    patterns = [

        r'(\d{2,5})\s?kr',

        r'(\d{2,5})\s?kroner',

        r'kr\.?\s?(\d{2,5})',

        r'(\d{2,5}),-',

        r'(\d{2,5})\s?dkk'
    ]

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

    prices = sorted(
        list(set(prices))
    )

    print(f"FOUND [{source}]:", prices)

    return prices

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if not prices:
        return []

    if len(prices) < 3:
        return prices

    median = statistics.median(
        prices
    )

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

    rounded = (
        round(median / 50) * 50
    )

    return f"{rounded} kr"

# ---------------------------------------------------
# ANALYZE
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
            ""
        )

        search_term = vision.get(
            "search_term",
            title
        )

        results = await serp_search(
            search_term
        )

        all_prices = []

        for result in results:

            source = result["source"]

            data = result["data"]

            found = extract_prices(
                source,
                data
            )

            all_prices.extend(found)

        all_prices = sorted(
            list(set(all_prices))
        )

        print("ALL:", all_prices)

        cleaned = clean_prices(
            all_prices
        )

        return {

            "title": title,

            "category": category,

            "condition": condition,

            "price": build_price(
                cleaned
            ),

            "matches": len(cleaned)

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