print("🔥 AI PRICING AGENT v8 🔥")

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import io
import re
from statistics import median
from PIL import Image
import base64

# Gemini (optional fallback)
try:
    from google import genai
    GEMINI_ENABLED = True
except:
    GEMINI_ENABLED = False

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_ENABLED and GEMINI_API_KEY:
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
    except:
        return image_bytes


# -------------------------
# 🔍 GOOGLE LENS (PRIMARY)
# -------------------------
def search_lens(image_bytes):
    try:
        url = "https://serpapi.com/search.json"

        files = {"image": ("image.jpg", image_bytes)}

        params = {
            "engine": "google_lens",
            "api_key": SERPAPI_KEY,
            "hl": "da",
            "gl": "dk"
        }

        res = requests.post(url, files=files, params=params, timeout=15)

        if res.status_code != 200:
            print("❌ Lens HTTP:", res.status_code)
            return []

        data = res.json()

        keywords = []

        for r in data.get("visual_matches", [])[:5]:
            title = r.get("title", "")
            if title:
                keywords.append(title.lower())

        print("🔎 LENS:", keywords)

        return keywords

    except Exception as e:
        print("Lens fejl:", e)
        return []


# -------------------------
# 🔍 GEMINI FALLBACK
# -------------------------
def detect_object_gemini(image_bytes):
    if not GEMINI_ENABLED or not GEMINI_API_KEY:
        return "genstand", ["brugt genstand"]

    try:
        b64 = base64.b64encode(image_bytes).decode()

        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=[
                {"text": "Hvad er dette objekt? Svar kort på dansk."},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64
                    }
                }
            ]
        )

        text = response.text.strip()
        print("🔥 GEMINI:", text)

        return text, [text]

    except Exception as e:
        print("Gemini fejl:", e)
        return "genstand", ["brugt genstand"]


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

        res = requests.get("https://serpapi.com/search.json", params=params, timeout=10)

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

    # 1. Lens FIRST
    lens_keywords = search_lens(img)

    if lens_keywords:
        keywords = lens_keywords
        name = lens_keywords[0]
    else:
        # 2. Gemini fallback
        name, keywords = detect_object_gemini(img)

    print("🔎 SEARCH TERMS:", keywords)

    prices = []

    for kw in keywords[:3]:
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
    return {"status": "ok", "version": "v8"}