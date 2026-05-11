# main.py

````python
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
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

print("GEMINI:", bool(GEMINI_API_KEY))
print("VISION:", bool(GOOGLE_VISION_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))

# ---------------------------------------------------
# GEMINI
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# CONSTANTS
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
    "flet",
]

CATEGORY_WORDS = [
    "sofa",
    "stol",
    "lænestol",
    "spisebord",
    "bord",
    "lampe",
    "pendel",
    "vase",
    "reol",
    "kommode",
]

REMOVE_WORDS = [
    "brugt",
    "god stand",
    "flot stand",
    "velholdt",
    "unik",
    "sjælden",
    "patina",
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
    print(f"IMAGE: {len(image_bytes)} -> {len(optimized)} bytes")
    print("=" * 40)

    return optimized

# ---------------------------------------------------
# GOOGLE LENS
# ---------------------------------------------------

async def google_lens_search(image_bytes):

    try:

        print("=" * 40)
        print("GOOGLE LENS SEARCH")
        print("=" * 40)

        image_base64 = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        image_data_url = (
            f"data:image/jpeg;base64,{image_base64}"
        )

        url = "https://serpapi.com/search.json"

        params = {
            "engine": "google_lens",
            "url": image_data_url,
            "api_key": SERPAPI_KEY
        }

        async with httpx.AsyncClient(timeout=60) as http:

            response = await http.get(
                url,
                params=params
            )

        data = response.json()

        candidates = []

        # ---------------------------------------------------
        # KNOWLEDGE GRAPH
        # ---------------------------------------------------

        knowledge = data.get(
            "knowledge_graph",
            {}
        )

        if knowledge:

            kg_title = knowledge.get("title")

            if kg_title:
                candidates.append(kg_title)

        # ---------------------------------------------------
        # VISUAL MATCHES
        # ---------------------------------------------------

        visual_matches = data.get(
            "visual_matches",
            []
        )

        for item in visual_matches[:10]:

            title = item.get("title", "")

            if len(title) > 3:
                candidates.append(title)

        # ---------------------------------------------------
        # CLEAN
        # ---------------------------------------------------

        cleaned = []

        for candidate in candidates:

            candidate = candidate.strip()

            if len(candidate) < 3:
                continue

            if candidate not in cleaned:
                cleaned.append(candidate)

        print("=" * 40)
        print("LENS CANDIDATES")
        print(cleaned[:10])
        print("=" * 40)

        return cleaned

    except Exception as e:

        print("LENS ERROR:", e)

        return []

# ---------------------------------------------------
# GEMINI NORMALIZATION
# ---------------------------------------------------

async def normalize_search_term(
    lens_candidates
):

    prompt = f"""
Du får Google Lens resultater.

Find den bedste DBA-søgning.

REGLER:
- Kort
- Menneskeligt DBA-sprog
- Max 3 ord
- Behold brand/modeller hvis de er stærke
- Fjern støj
- Dansk hvis muligt

Lens resultater:
{lens_candidates}

Returnér KUN valid JSON:

{{
  "title": "Kort titel",
  "search_term": "DBA søgning",
  "category": "Kategori",
  "modifier": "Vigtig modifier eller tom"
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
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

    print("=" * 40)
    print("NORMALIZED")
    print(text)
    print("=" * 40)

    return json.loads(text)

# ---------------------------------------------------
# SMART SEARCH
# ---------------------------------------------------

def build_search_query(search_term):

    search_term = search_term.lower()

    for word in REMOVE_WORDS:

        search_term = re.sub(
            rf"\\b{re.escape(word)}\\b",
            "",
            search_term,
            flags=re.IGNORECASE
        )

    search_term = re.sub(
        r"\s+",
        " ",
        search_term
    ).strip()

    print("=" * 40)
    print("FINAL SEARCH")
    print(search_term)
    print("=" * 40)

    return search_term

# ---------------------------------------------------
# DBA SEARCH
# ---------------------------------------------------

async def dba_search(query):

    try:

        print("=" * 40)
        print(f"DBA SEARCH: {query}")
        print("=" * 40)

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

        async with httpx.AsyncClient(timeout=30) as http:

            response = await http.get(
                url,
                headers=headers
            )

        html = response.text

        print("=" * 40)
        print(f"HTML LENGTH: {len(html)}")
        print("=" * 40)

        # ---------------------------------------------------
        # GLOBAL PRICE EXTRACTION
        # ---------------------------------------------------

        matches = re.findall(
            r"(\d{1,3}(?:\.\d{3})*)\s?kr",
            html,
            flags=re.IGNORECASE
        )

        prices = []

        for raw in matches:

            try:

                raw = raw.replace(".", "")
                raw = raw.replace(",", "")

                price = int(raw)

                if 50 <= price <= 250000:
                    prices.append(price)

            except:
                pass

        prices = sorted(list(set(prices)))

        print("=" * 40)
        print(f"RAW PRICES: {prices[:50]}")
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

    if len(prices) < 5:
        return sorted(prices)

    median = statistics.median(prices)

    filtered = []

    for price in prices:

        deviation = abs(price - median) / median

        if deviation <= 0.60:

            filtered.append(price)

        else:

            print(f"OUTLIER REMOVED: {price}")

    filtered = sorted(list(set(filtered)))

    print("FILTERED:", filtered)

    return filtered

# ---------------------------------------------------
# PRICE RANGE
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

        optimized = optimize_image(
            image_bytes
        )

        # ---------------------------------------------------
        # GOOGLE LENS
        # ---------------------------------------------------

        lens_candidates = await google_lens_search(
            optimized
        )

        # ---------------------------------------------------
        # FALLBACK IF LENS FAILS
        # ---------------------------------------------------

        if not lens_candidates:

            lens_candidates = [
                "brugt møbel"
            ]

        # ---------------------------------------------------
        # NORMALIZE
        # ---------------------------------------------------

        normalized = await normalize_search_term(
            lens_candidates
        )

        title = normalized.get(
            "title",
            "Ukendt"
        )

        category = normalized.get(
            "category",
            "Andet"
        )

        search_term = normalized.get(
            "search_term",
            title
        )

        modifier = normalized.get(
            "modifier",
            ""
        )

        # ---------------------------------------------------
        # FINAL QUERY
        # ---------------------------------------------------

        final_query = build_search_query(
            search_term
        )

        # ---------------------------------------------------
        # DBA SEARCH
        # ---------------------------------------------------

        prices = await dba_search(
            final_query
        )

        filtered = clean_prices(prices)

        price_range = build_price_range(
            filtered
        )

        return {
            "title": title,
            "category": category,
            "modifier": modifier,
            "search_term": final_query,
            "price": (
                price_range
                if price_range
                else "Ingen sikre priser fundet"
            ),
            "lens_matches": lens_candidates[:5]
        }

    except Exception as e:

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )
````

---

# requirements.txt

```txt
fastapi
uvicorn
google-genai
pillow
httpx
python-multipart
```
