print("🔥 AI PRICING AGENT v7 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import io
import re
from statistics import median
from PIL import Image
import base64

# NEW SDK
from google import genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


# -------------------------
# 🖼️ KOMPRESS
# -------------------------
def compress_image(image_bytes, max_size=800):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_size, max_size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        compressed = buf.getvalue()
        print(f"📦 COMPRESSED: {len(image_bytes)} → {len(compressed)}")
        return compressed
    except Exception as e:
        print("❌ Compress fejl:", e)
        return image_bytes


# -------------------------
# 🔍 GEMINI (NY SDK)
# -------------------------
def detect_object(image_bytes):
    try:
        b64 = base64.b64encode(image_bytes).decode()

        prompt = """
Du ser et billede fra en genbrugsbutik i Danmark.

Returnér KUN JSON:

{
 "name": "kort dansk navn (max 3 ord)",
 "keywords": ["søgeord1", "søgeord2", "søgeord3"]
}

Svar KUN JSON. Ingen forklaring.
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64
                    }
                }
            ]
        )

        text = response.text.strip()
        print("🔥 GEMINI RAW:", text)

        import json

        try:
            data = json.loads(text)
        except:
            text = text.replace("```json", "").replace("```", "")
            data = json.loads(text)

        name = data.get("name", "genstand")
        keywords = data.get("keywords", [name])

        return name, keywords

    except Exception as e:
        print("🚨 GEMINI FEJL:", e)
        return "genstand", ["brugt genstand", "til salg"]


# -------------------------
# 🔍 GOOGLE LENS (SerpAPI)
# -------------------------
def search_lens(image_bytes):
    try:
        url = "https://serpapi.com/search"

        files = {"image": ("image.jpg", image_bytes)}

        params = {
            "engine": "google_lens",
            "api_key": SERPAPI_KEY,
            "hl": "da",
            "gl": "dk"
        }

        res = requests.post(url, files=files, params=params, timeout=15)
        data = res.json()

        keywords = []

        for r in data.get("visual_matches", [])[:5]:
            title = r.get("title", "")
            if title:
                keywords.append(title.lower())

        print("🔎 LENS KEYWORDS:", keywords)

        return keywords

    except Exception as e:
        print("Lens fejl:", e)
        return []


# -------------------------
# 💰 PRISSØGNING
# -------------------------
def search_prices(query):
    try:
        params = {
            "engine": "google",
            "q": f"site:dba.dk {query}",
            "api_key": SERPAPI_KEY,
            "gl": "dk",
            "hl": "da"
        }

        res = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data = res.json()

        prices = []

        for r in data.get("organic_results", []):
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()

            matches = re.findall(r'(\d[\d.]{1,6})\s*(kr|,-)', text)

            for m in matches:
                price = int(m[0].replace(".", ""))
                if 25 < price < 20000:
                    prices.append(price)

        return prices

    except Exception as e:
        print("Pris fejl:", e)
        return []


# -------------------------
# 🚀 ENDPOINT
# -------------------------
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    print("=== /analyze ===")

    contents = await file.read()
    print(f"📷 SIZE: {len(contents)}")

    img = compress_image(contents)

    # 1. Gemini
    name, keywords = detect_object(img)

    # 2. Lens backup
    lens_keywords = search_lens(img)

    all_keywords = keywords + lens_keywords
    print("🔎 FINAL SEARCH TERMS:", all_keywords)

    prices = []

    for kw in all_keywords[:3]:
        print("🔍 SEARCH:", kw)
        prices.extend(search_prices(kw))

    if prices:
        prices.sort()
        final = int(median(prices))
        return {
            "description": name,
            "price": f"{final} kr",
            "hits": len(prices)
        }

    return {
        "description": name,
        "price": "Ingen data",
        "hits": 0
    }


@app.get("/")
def root():
    return {"status": "ok", "version": "v7"}