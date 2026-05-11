from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from google import genai
from google.genai import types

from PIL import Image

import cloudinary
import cloudinary.uploader

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

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

print("GEMINI:", bool(GEMINI_API_KEY))
print("SERPAPI:", bool(SERPAPI_KEY))
print("CLOUDINARY:", bool(CLOUDINARY_CLOUD_NAME))

# ---------------------------------------------------
# GEMINI
# ---------------------------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------
# CLOUDINARY
# ---------------------------------------------------

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
)

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
# GOOGLE LENS SEARCH
# ---------------------------------------------------

async def google_lens_search(image_bytes):

    try:

        print("=" * 40)
        print("GOOGLE LENS SEARCH")
        print("=" * 40)

        # -----------------------------------------
        # UPLOAD TO CLOUDINARY
        # -----------------------------------------

        upload_result = cloudinary.uploader.upload(
            image_bytes,
            folder="pricing-agent",
            resource_type="image"
        )

        image_url = upload_result.get("secure_url")

        print("=" * 40)
        print("IMAGE URL")
        print(image_url)
        print("=" * 40)

        # -----------------------------------------
        # SERPAPI GOOGLE LENS
        # -----------------------------------------

        url = "https://serpapi.com/search.json"

        params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": SERPAPI_KEY
        }

        async with httpx.AsyncClient(timeout=60) as http:

            response = await http.get(
                url,
                params=params
            )

        data = response.json()

        print("=" * 40)
        print("LENS RESPONSE")
        print(json.dumps(data)[:2000])
        print("=" * 40)

        candidates = []

        # -----------------------------------------
        # KNOWLEDGE GRAPH
        # -----------------------------------------

        knowledge = data.get(
            "knowledge_graph",
            {}
        )

        if knowledge:

            title = knowledge.get("title")

            if title:
                candidates.append(title)

        # -----------------------------------------
        # VISUAL MATCHES
        # -----------------------------------------

        visual_matches = data.get(
            "visual_matches",
            []
        )

        for item in visual_matches[:10]:

            title = item.get("title", "")

            if len(title) > 3:
                candidates.append(title)

        # -----------------------------------------
        # CLEAN
        # -----------------------------------------

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

        traceback.print_exc()

        return []

# ---------------------------------------------------
# NORMALIZE SEARCH TERM
# ---------------------------------------------------

async def normalize_search_term(lens_candidates):

    try:

        prompt = f"""
Du får Google Lens resultater.

Find den bedste DBA søgning.

REGLER:
- Kort
- Max 3 ord
- Dansk hvis muligt
- Brug modelnavne hvis sikre
- Fjern støj

Lens resultater:
{lens_candidates}

Returnér KUN valid JSON:

{{
  "title": "Kort titel",
  "search_term": "DBA søgning",
  "category": "Kategori"
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

    except Exception as e:

        print("NORMALIZE ERROR:", e)

        fallback = ""

        if lens_candidates:

            fallback = lens_candidates[0]

            fallback = fallback.lower()

            fallback = re.sub(
                r"[^a-zA-ZæøåÆØÅ0-9 ]",
                " ",
                fallback
            )

            remove_words = [
                "with",
                "lights",
                "light",
                "lamp",
                "ceiling",
                "modern",
                "indoor",
                "farmhouse",
                "boho",
                "large",
                "small",
                "set",
                "premium",
                "linen",
                "mount",
                "flush",
                "semi",
                "profile",
                "remote",
                "usa"
            ]

            for word in remove_words:

                fallback = re.sub(
                    rf"\b{word}\b",
                    "",
                    fallback
                )

            fallback = re.sub(
                r"\s+",
                " ",
                fallback
            ).strip()

            words = fallback.split(" ")

            fallback = " ".join(words[:3])

        if not fallback:
            fallback = "lampe"

        print("=" * 40)
        print("FALLBACK SEARCH")
        print(fallback)
        print("=" * 40)

        return {
            "title": fallback.title(),
            "search_term": fallback,
            "category": "Møbler"
        }

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
        print("RAW PRICES")
        print(prices[:50])
        print(f"COUNT: {len(prices)}")
        print("=" * 40)

        return prices

    except Exception as e:

        print("DBA ERROR:", e)

        return []

# ---------------------------------------------------
# CLEAN PRICES
# ---------------------------------------------------

def clean_prices(prices):

    if not prices:
        return []

    if len(prices) < 5:
        return prices

    median = statistics.median(prices)

    filtered = []

    for price in prices:

        deviation = abs(price - median) / median

        if deviation <= 0.60:

            filtered.append(price)

        else:

            print(f"OUTLIER REMOVED: {price}")

    filtered = sorted(list(set(filtered)))

    print("=" * 40)
    print("FILTERED")
    print(filtered)
    print("=" * 40)

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

        optimized = optimize_image(image_bytes)

        # -----------------------------------------
        # GOOGLE LENS
        # -----------------------------------------

        lens_candidates = await google_lens_search(
            optimized
        )

        # -----------------------------------------
        # FALLBACK
        # -----------------------------------------

        if not lens_candidates:

            lens_candidates = [
                "lampe"
            ]

        # -----------------------------------------
        # NORMALIZE
        # -----------------------------------------

        normalized = await normalize_search_term(
            lens_candidates
        )

        title = normalized.get(
            "title",
            "Ukendt"
        )

        category = normalized.get(
            "category",
            "Møbler"
        )

        search_term = normalized.get(
            "search_term",
            title
        )

        # -----------------------------------------
        # DBA SEARCH
        # -----------------------------------------

        prices = await dba_search(
            search_term
        )

        filtered = clean_prices(prices)

        price_range = build_price_range(
            filtered
        )

        return {
            "title": title,
            "category": category,
            "search_term": search_term,
            "price": (
                price_range
                if price_range
                else "Ingen sikre priser fundet"
            ),
            "lens_matches": lens_candidates[:5],
            "sample_prices": filtered[:15]
        }

    except Exception as e:

        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )